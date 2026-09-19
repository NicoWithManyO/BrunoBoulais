"""Côté Django : lancement et pilotage des démons PTY (cf. daemon.py).

Une session console = un identifiant opaque (posé dans la session Django) + un
socket unix dans ``CONSOLE_RUNTIME_DIR``. Les vues ne font que relayer des
requêtes JSON ; tout l'état vit dans le démon.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import secrets
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

# Les identifiants de session sont générés ici, mais ils transitent par la
# session Django : on les revalide avant de construire un chemin de fichier.
SID_RE = re.compile(r"\A[0-9a-f]{16}\Z")
CONNECT_TIMEOUT = 5.0
SPAWN_TIMEOUT = 10.0


class ConsoleError(RuntimeError):
    """Le démon est injoignable (pas encore lancé, mort, ou socket périmé)."""


def new_sid() -> str:
    return secrets.token_hex(8)


def runtime_dir() -> Path:
    path = Path(settings.CONSOLE_RUNTIME_DIR)
    path.mkdir(parents=True, exist_ok=True)
    # Les sockets donnent un shell : personne d'autre que l'utilisateur du
    # site n'a à entrer dans ce dossier.
    os.chmod(path, 0o700)
    return path


def _paths(sid: str):
    if not SID_RE.match(sid or ""):
        raise ConsoleError("identifiant de session invalide")
    base = runtime_dir() / sid
    return base.with_suffix(".sock"), base.with_suffix(".lock"), base.with_suffix(".log")


def _shell_argv() -> list[str]:
    argv = settings.CONSOLE_SHELL
    return shlex.split(argv) if isinstance(argv, str) else list(argv)


def _locale_env() -> list[str]:
    """Force une locale UTF-8 si le process web n'en a pas.

    Sans locale UTF-8, les accents ressortent en « ? » dans le terminal. On
    n'écrase jamais une locale déjà posée (celle du site est la bonne), et on
    pose ``LANG`` et pas ``LC_ALL`` : ``LC_ALL`` écraserait tout, y compris une
    locale que l'utilisateur règle dans son ``.bashrc``.
    """
    current = os.environ.get("LC_ALL") or os.environ.get("LANG") or ""
    if "utf" in current.lower():
        return []
    return ["--env", f"LANG={settings.CONSOLE_LOCALE}"]


def request(sid: str, payload: dict) -> dict:
    """Une requête JSON sur le socket du démon. Lève ConsoleError si injoignable."""
    sock_path, _, _ = _paths(sid)
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(CONNECT_TIMEOUT + float(payload.get("wait") or 0.0))
    try:
        try:
            conn.connect(str(sock_path))
        except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
            raise ConsoleError("session fermée") from exc
        conn.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        chunks = bytearray()
        while b"\n" not in chunks:
            data = conn.recv(65536)
            if not data:
                raise ConsoleError("réponse tronquée")
            chunks += data
    except OSError as exc:
        raise ConsoleError(str(exc)) from exc
    finally:
        conn.close()
    try:
        return json.loads(bytes(chunks.split(b"\n", 1)[0]))
    except ValueError as exc:
        raise ConsoleError("réponse illisible") from exc


def alive(sid: str) -> bool:
    try:
        return bool(request(sid, {"op": "ping"}).get("alive"))
    except ConsoleError:
        return False


def start(sid: str) -> None:
    """Lance le démon pour ``sid`` et attend qu'il réponde.

    Détaché (``start_new_session``) pour survivre au redémarrage de gunicorn,
    et sans fd hérité : le démon ne doit rien garder ouvert du worker web.
    """
    sock_path, lock_path, log_path = _paths(sid)
    argv = [
        sys.executable,
        "-m",
        "apps.console.daemon",
        "--socket",
        str(sock_path),
        "--lock",
        str(lock_path),
        "--cwd",
        str(settings.CONSOLE_CWD),
        "--idle-timeout",
        str(settings.CONSOLE_IDLE_TIMEOUT),
        "--max-lifetime",
        str(settings.CONSOLE_MAX_LIFETIME),
        "--env",
        "TERM=xterm-256color",
        "--env",
        "COLORTERM=truecolor",
        *_locale_env(),
        "--",
        *_shell_argv(),
    ]
    with open(log_path, "ab", buffering=0) as log:
        subprocess.Popen(  # noqa: S603 — argv construit depuis les settings, pas depuis la requête
            argv,
            cwd=str(settings.BASE_DIR),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            close_fds=True,
        )

    deadline = time.monotonic() + SPAWN_TIMEOUT
    while time.monotonic() < deadline:
        try:
            if request(sid, {"op": "ping"}).get("ok"):
                return
        except ConsoleError:
            time.sleep(0.05)
    raise ConsoleError(f"le démon n'a pas démarré (voir {log_path.name})")


def ensure(sid: str) -> None:
    """Démarre le démon si besoin ; no-op s'il répond déjà."""
    try:
        if request(sid, {"op": "ping"}).get("ok"):
            return
    except ConsoleError:
        pass
    start(sid)


def io(sid: str, *, data: bytes = b"", since=None, wait: float = 0.0, cols=None, rows=None) -> dict:
    payload = {
        "op": "io",
        "in": base64.b64encode(data).decode("ascii") if data else "",
        "since": since,
        "wait": wait,
    }
    if cols and rows:
        payload["cols"], payload["rows"] = int(cols), int(rows)
    return request(sid, payload)


def kill(sid: str) -> None:
    try:
        request(sid, {"op": "kill"})
    except ConsoleError:
        pass
