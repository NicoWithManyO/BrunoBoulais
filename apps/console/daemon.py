"""Démon PTY : un process détaché par session console, piloté via socket unix.

Pourquoi un process séparé plutôt qu'un PTY gardé en mémoire dans le worker
gunicorn :

* gunicorn recycle ses workers (``max-requests``, reload gracieux au
  déploiement). Un PTY vivant dans le worker mourrait avec lui — donc en plein
  ``git pull`` ou ``migrate`` lancé depuis la console. Ici le démon est détaché
  (``start_new_session``) : on recharge la page et on retrouve son shell.
  (Un ``systemctl restart`` emporte quand même le démon si l'unité est en
  ``KillMode=control-group``, le défaut — cf. to-prod-console.md.)
* si un jour gunicorn tourne à plusieurs workers, n'importe lequel peut parler
  au démon via le socket unix — pas d'affinité de session à gérer.

Protocole : une requête JSON par connexion, terminée par ``\\n``, réponse JSON
terminée par ``\\n``. Volontairement synchrone et sans état côté client : le
client ne garde qu'un offset d'octets (``since``), ce qui rend la reconnexion
après coupure réseau triviale (le réseau d'entreprise derrière lequel tourne
tout ça coupe volontiers les requêtes longues).

    {"op": "ping"}
        -> {"ok": true, "alive": true, "seq": 1234}
    {"op": "io", "in": "<b64>", "since": 1234, "wait": 0.0,
     "cols": 120, "rows": 32}
        -> {"ok": true, "seq": 1290, "out": "<b64>", "reset": false,
            "alive": true, "exit": null}
    {"op": "kill"}
        -> {"ok": true}

``since`` est un index absolu en octets depuis le début de la session ; le
démon ne garde que les ``BUFFER_MAX`` derniers octets, et répond
``reset: true`` quand le client a pris trop de retard (le client redessine
alors son terminal à partir du buffer renvoyé).

Ce module est du stdlib pur : il tourne hors de Django (``python -m
apps.console.daemon``), donc pas d'import du projet ici.
"""

from __future__ import annotations

import argparse
import base64
import errno
import fcntl
import json
import logging
import os
import pty
import signal
import socket
import struct
import sys
import termios
import threading
import time

logger = logging.getLogger("console.daemon")

# Scrollback conservé côté démon. Sert au rattrapage après une coupure réseau
# ou un rechargement de page, pas de scrollback « infini » : xterm garde
# l'historique côté navigateur une fois les octets reçus.
BUFFER_MAX = 512 * 1024
READ_CHUNK = 65536
# Cap sur une requête entrante (une frappe clavier ou un coller).
REQUEST_MAX = 1024 * 1024
# Plafond du temps qu'une requête peut passer à attendre de la sortie. Le
# client appelle normalement avec wait=0 (cf. apps/console/views.py : gunicorn
# tourne à un seul worker, on ne bloque pas le site pour un terminal).
WAIT_MAX = 20.0


class PtySession:
    """Le shell et son PTY, plus le buffer de sortie partagé entre threads."""

    def __init__(self, argv, cwd, env, *, idle_timeout, max_lifetime):
        self.argv = argv
        self.idle_timeout = idle_timeout
        self.max_lifetime = max_lifetime

        self._cond = threading.Condition()
        self._buf = bytearray()
        self._start = 0  # index absolu du premier octet encore en buffer
        self._seq = 0  # nombre total d'octets produits depuis le début
        self._alive = True
        self._exit = None
        self._started = time.monotonic()
        self._last_contact = self._started

        # fork AVANT de démarrer le moindre thread : forker un process
        # multi-threadé n'est sûr que jusqu'au exec, et on veut aussi que
        # l'enfant n'hérite d'aucun verrou pris par un thread.
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            self._exec_child(argv, cwd, env)  # ne revient jamais
        os.set_blocking(self.fd, True)

    @staticmethod
    def _exec_child(argv, cwd, env):
        try:
            os.chdir(cwd)
        except OSError:
            pass  # cwd disparu : on démarre dans le cwd hérité plutôt que rien
        try:
            os.execvpe(argv[0], argv, env)
        except OSError as exc:
            # stderr de l'enfant = le PTY : le message arrive dans le terminal
            # du navigateur, ce qui est exactement ce qu'on veut voir.
            sys.stderr.write(f"console: impossible de lancer {argv[0]!r} : {exc}\r\n")
            sys.stderr.flush()
        os._exit(127)

    # --- production de sortie --------------------------------------------

    def pump(self):
        """Boucle de lecture du PTY (thread dédié), jusqu'à la mort du shell."""
        while True:
            try:
                data = os.read(self.fd, READ_CHUNK)
            except OSError as exc:
                # EIO = l'esclave a été fermé, c'est la fin normale côté Linux.
                if exc.errno not in (errno.EIO, errno.EBADF):
                    logger.warning("lecture PTY: %s", exc)
                data = b""
            if not data:
                break
            with self._cond:
                self._buf += data
                self._seq += len(data)
                overflow = len(self._buf) - BUFFER_MAX
                if overflow > 0:
                    del self._buf[:overflow]
                    self._start += overflow
                self._cond.notify_all()
        self._reap()

    def _reap(self):
        status = None
        try:
            _, status = os.waitpid(self.pid, 0)
        except ChildProcessError:
            pass
        with self._cond:
            self._alive = False
            if status is not None:
                self._exit = (
                    os.waitstatus_to_exitcode(status)
                    if hasattr(os, "waitstatus_to_exitcode")
                    else status
                )
            self._cond.notify_all()

    # --- API appelée par les connexions ----------------------------------

    def touch(self):
        with self._cond:
            self._last_contact = time.monotonic()

    def write(self, data: bytes):
        if not data:
            return
        with self._cond:
            if not self._alive:
                return
        try:
            while data:
                written = os.write(self.fd, data)
                data = data[written:]
        except OSError as exc:
            if exc.errno not in (errno.EIO, errno.EBADF, errno.EPIPE):
                logger.warning("écriture PTY: %s", exc)

    def resize(self, rows: int, cols: int):
        rows = max(1, min(int(rows), 500))
        cols = max(2, min(int(cols), 1000))
        try:
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        except OSError:
            return
        # Le kernel envoie déjà SIGWINCH au groupe de la session ; le renvoyer
        # explicitement ne coûte rien et réveille les shells qui l'ignorent.
        try:
            os.killpg(self.pid, signal.SIGWINCH)
        except OSError:
            pass

    def read(self, since, wait: float):
        """Octets produits depuis ``since`` (None = tout le buffer courant)."""
        deadline = time.monotonic() + max(0.0, min(wait, WAIT_MAX))
        with self._cond:
            while True:
                if since is None or since < self._start:
                    reset, out = True, bytes(self._buf)
                else:
                    reset, out = False, bytes(self._buf[since - self._start :])
                remaining = deadline - time.monotonic()
                if out or not self._alive or remaining <= 0:
                    return {
                        "seq": self._seq,
                        "out": base64.b64encode(out).decode("ascii"),
                        "reset": reset,
                        "alive": self._alive,
                        "exit": self._exit,
                    }
                self._cond.wait(min(0.25, remaining))

    def status(self):
        with self._cond:
            return {"alive": self._alive, "seq": self._seq, "exit": self._exit}

    # --- fin de vie -------------------------------------------------------

    def expired(self):
        """(raison, True) si la session doit être fermée d'office."""
        with self._cond:
            now = time.monotonic()
            if not self._alive:
                return "shell terminé"
            if self.idle_timeout and now - self._last_contact > self.idle_timeout:
                return "inactivité"
            if self.max_lifetime and now - self._started > self.max_lifetime:
                return "durée maximale atteinte"
        return None

    def terminate(self):
        """SIGHUP au groupe du shell (comme une liaison série coupée), puis SIGKILL."""
        for sig in (signal.SIGHUP, signal.SIGKILL):
            with self._cond:
                if not self._alive:
                    return
            try:
                os.killpg(self.pid, sig)
            except OSError:
                return
            for _ in range(20):
                with self._cond:
                    if not self._alive:
                        return
                time.sleep(0.1)


class Server:
    """Socket unix + dispatch des requêtes JSON vers la session."""

    def __init__(self, session: PtySession, sock: socket.socket):
        self.session = session
        self.sock = sock
        self.stop = threading.Event()

    def serve(self):
        self.sock.settimeout(0.5)
        while not self.stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket):
        try:
            conn.settimeout(WAIT_MAX + 10)
            payload = self._read_request(conn)
            if payload is None:
                return
            try:
                response = self._dispatch(payload)
            except Exception as exc:  # noqa: BLE001 — jamais tuer le démon pour une requête
                logger.exception("requête console en erreur")
                response = {"ok": False, "error": str(exc)}
            conn.sendall(json.dumps(response).encode("utf-8") + b"\n")
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    @staticmethod
    def _read_request(conn):
        chunks = bytearray()
        while b"\n" not in chunks:
            try:
                data = conn.recv(READ_CHUNK)
            except OSError:
                return None
            if not data:
                return None
            chunks += data
            if len(chunks) > REQUEST_MAX:
                return None
        try:
            return json.loads(bytes(chunks.split(b"\n", 1)[0]))
        except ValueError:
            return None

    def _dispatch(self, req):
        op = req.get("op")
        session = self.session
        session.touch()

        if op == "ping":
            return {"ok": True, **session.status()}

        if op == "kill":
            threading.Thread(
                target=self.shutdown, args=("fermeture demandée",), daemon=True
            ).start()
            return {"ok": True}

        if op != "io":
            return {"ok": False, "error": f"op inconnue: {op!r}"}

        cols, rows = req.get("cols"), req.get("rows")
        if cols and rows:
            session.resize(rows, cols)
        data = req.get("in") or ""
        if data:
            session.write(base64.b64decode(data))
        since = req.get("since")
        if since is False:
            # Envoi seul (frappe clavier) : la boucle de lecture du client
            # ramassera l'écho, inutile de dupliquer la sortie ici.
            return {"ok": True, **session.status()}
        return {"ok": True, **session.read(since, float(req.get("wait") or 0.0))}

    def shutdown(self, reason):
        logger.info("arrêt de la session (%s)", reason)
        self.stop.set()
        self.session.terminate()
        try:
            self.sock.close()
        except OSError:
            pass


def _janitor(server: Server):
    while not server.stop.wait(1.0):
        reason = server.session.expired()
        if reason:
            server.shutdown(reason)
            return


def _bind(socket_path: str, lock_path: str):
    """Socket unix 0600, protégé par un flock pour éviter deux démons par session."""
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(lock_fd)
        return None, None
    # On tient le verrou : un éventuel socket restant est forcément orphelin.
    try:
        os.unlink(socket_path)
    except FileNotFoundError:
        pass
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old_umask = os.umask(0o177)
    try:
        sock.bind(socket_path)
    finally:
        os.umask(old_umask)
    sock.listen(16)
    return sock, lock_fd


def main(argv=None):
    parser = argparse.ArgumentParser(description="Démon PTY de la console web")
    parser.add_argument("--socket", required=True)
    parser.add_argument("--lock", required=True)
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--idle-timeout", type=float, default=1800.0)
    parser.add_argument("--max-lifetime", type=float, default=12 * 3600.0)
    parser.add_argument("--env", action="append", default=[], metavar="CLE=VALEUR")
    parser.add_argument("shell", nargs="+")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s console.daemon[%(process)d]: %(message)s",
    )

    sock, lock_fd = _bind(args.socket, args.lock)
    if sock is None:
        # Un autre worker a gagné la course : sa session est la bonne.
        logger.info("session déjà servie par un autre démon, sortie")
        return 3

    env = dict(os.environ)
    for item in args.env:
        key, _, value = item.partition("=")
        if key:
            env[key] = value

    session = PtySession(
        args.shell,
        args.cwd,
        env,
        idle_timeout=args.idle_timeout,
        max_lifetime=args.max_lifetime,
    )
    server = Server(session, sock)
    logger.info("session ouverte (pid shell=%s, shell=%s)", session.pid, args.shell)

    threading.Thread(target=session.pump, daemon=True).start()
    threading.Thread(target=_janitor, args=(server,), daemon=True).start()

    def _on_signal(_signum, _frame):
        threading.Thread(target=server.shutdown, args=("signal reçu",), daemon=True).start()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    try:
        server.serve()
    finally:
        server.stop.set()
        session.terminate()
        for path in (args.socket, args.lock):
            try:
                os.unlink(path)
            except OSError:
                pass
        os.close(lock_fd)
    logger.info("session fermée")
    return 0


if __name__ == "__main__":
    sys.exit(main())
