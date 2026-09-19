/* Console web : terminal xterm.js branché sur le PTY du serveur via HTTPS.
 *
 * Pas de WebSocket — uniquement des POST JSON, pour traverser les proxys
 * d'entreprise qui filtrent l'upgrade WebSocket autant que le port 22.
 *
 * Deux flux indépendants sur le même endpoint :
 *   - une boucle de lecture qui réclame les octets produits depuis `since` ;
 *   - un envoi immédiat des frappes (`since: false`, écriture seule), pour
 *     que la latence de l'écho soit celle d'un aller-retour et pas celle du
 *     prochain tick de la boucle.
 *
 * Le rythme de la boucle s'adapte : rapide juste après une frappe ou de la
 * sortie, lent quand rien ne bouge, très lent si l'onglet est en arrière-plan.
 * Le serveur (gunicorn, un seul worker) ne doit jamais être bloqué en attente.
 */
(function () {
  "use strict";

  var cfg = JSON.parse(document.getElementById("console-config").textContent);

  var statusEl = document.getElementById("console-status");
  var hintEl = document.getElementById("console-hint");

  var term = new window.Terminal({
    fontFamily: '"JetBrains Mono", "SFMono-Regular", Menlo, Consolas, monospace',
    fontSize: 13,
    lineHeight: 1.2,
    cursorBlink: true,
    scrollback: 10000,
    allowTransparency: false,
    theme: {
      background: "#0f1115",
      foreground: "#d5d8de",
      cursor: "#e8b96a",
      selectionBackground: "#3a4152",
      black: "#0f1115",
      brightBlack: "#5b6270",
    },
  });
  var fit = new window.FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(document.getElementById("console-term"));
  fit.fit();
  term.focus();

  var since = null; // offset absolu en octets déjà affichés
  var running = true; // la boucle de lecture tourne
  var shellAlive = true;
  var opened = false; // le premier échange a-t-il eu lieu
  var lastActivity = Date.now();
  var failures = 0;
  var wake = null; // réveil de la temporisation entre deux lectures
  var pendingInput = []; // frappes en attente d'envoi
  var sending = false;

  // --- réseau ---------------------------------------------------------------

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": cfg.csrf,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(body || {}),
    }).then(function (response) {
      if (response.status === 403) {
        var err = new Error("locked");
        err.locked = true;
        throw err;
      }
      if (response.status === 409) {
        var gone = new Error("gone");
        gone.gone = true;
        throw gone;
      }
      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }
      return response.json();
    });
  }

  // --- affichage ------------------------------------------------------------

  function setStatus(text, kind) {
    statusEl.textContent = text;
    statusEl.dataset.kind = kind;
  }

  function b64ToBytes(b64) {
    var raw = atob(b64);
    var bytes = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) {
      bytes[i] = raw.charCodeAt(i);
    }
    return bytes;
  }

  function bytesToB64(bytes) {
    var chunk = "";
    for (var i = 0; i < bytes.length; i++) {
      chunk += String.fromCharCode(bytes[i]);
    }
    return btoa(chunk);
  }

  function apply(payload) {
    if (payload.reset) {
      // On a pris trop de retard : le serveur renvoie son buffer, on repart
      // d'un terminal propre plutôt que d'afficher un flux tronqué.
      term.reset();
    }
    if (payload.out) {
      term.write(b64ToBytes(payload.out));
      lastActivity = Date.now();
    }
    if (typeof payload.seq === "number") {
      since = payload.seq;
    }
    if (payload.alive === false) {
      shellAlive = false;
      running = false;
      var code = payload.exit === null || payload.exit === undefined ? "" : " (code " + payload.exit + ")";
      term.write("\r\n\x1b[33m— shell terminé" + code + " —\x1b[0m\r\n");
      setStatus("terminé", "dead");
      hint("Le shell s'est fermé. « Nouvelle session » en ouvre un autre.");
    }
  }

  function hint(text) {
    hintEl.textContent = text || "";
    hintEl.hidden = !text;
  }

  // --- boucle de lecture ----------------------------------------------------

  function interval() {
    if (document.hidden) return 5000;
    var idle = Date.now() - lastActivity;
    if (idle < 3000) return 120;
    if (idle < 30000) return 500;
    return 2000;
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      var timer = setTimeout(function () {
        wake = null;
        resolve();
      }, ms);
      wake = function () {
        clearTimeout(timer);
        wake = null;
        resolve();
      };
    });
  }

  function kick() {
    if (wake) wake();
  }

  function dimensions() {
    return { cols: term.cols, rows: term.rows };
  }

  function readLoop() {
    if (!running) return;
    var body = { since: since, wait: cfg.wait };
    var size = dimensions();
    body.cols = size.cols;
    body.rows = size.rows;
    if (!opened) body.open = true;

    post(cfg.io, body)
      .then(function (payload) {
        if (!opened) {
          opened = true;
          setStatus("connecté", "ok");
          hint("");
        }
        failures = 0;
        apply(payload);
      })
      .catch(handleError)
      .then(function () {
        if (!running) return;
        return sleep(interval()).then(readLoop);
      });
  }

  function handleError(err) {
    if (err && err.locked) {
      running = false;
      setStatus("verrouillé", "dead");
      hint("Session expirée : rechargez la page pour vous ré-authentifier.");
      return;
    }
    if (err && err.gone) {
      running = false;
      shellAlive = false;
      setStatus("session perdue", "dead");
      hint("Le shell n'existe plus côté serveur. « Nouvelle session » en ouvre un autre.");
      return;
    }
    // Coupure réseau : on garde la boucle, `since` fait le rattrapage tout
    // seul dès que ça repasse (rien n'est perdu tant que le démon vit).
    failures += 1;
    setStatus(failures > 2 ? "reconnexion…" : "connecté", failures > 2 ? "warn" : "ok");
    if (failures > 2) {
      lastActivity = 0; // force le rythme lent tant que ça ne répond pas
    }
  }

  // --- frappes --------------------------------------------------------------

  term.onData(function (data) {
    if (!shellAlive) return;
    pendingInput.push(data);
    lastActivity = Date.now();
    flush();
  });

  function flush() {
    if (sending || !pendingInput.length || !shellAlive) return;
    var data = pendingInput.join("");
    pendingInput = [];
    sending = true;
    post(cfg.io, { in: bytesToB64(new TextEncoder().encode(data)), since: false })
      .then(function () {
        kick(); // l'écho arrive juste derrière : relancer la lecture tout de suite
      })
      .catch(function (err) {
        // Frappes perdues : on ne les rejoue pas (rejouer à l'aveugle dans un
        // shell est pire que de les perdre), on signale seulement.
        handleError(err);
      })
      .then(function () {
        sending = false;
        flush();
      });
  }

  // --- redimensionnement ----------------------------------------------------

  var resizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      try {
        fit.fit();
      } catch (e) {
        /* terminal masqué */
      }
      kick(); // la nouvelle taille part avec la prochaine lecture
    }, 120);
  });

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) {
      lastActivity = Date.now();
      kick();
    }
  });

  document.getElementById("console-term").addEventListener("click", function () {
    term.focus();
  });

  // --- boutons --------------------------------------------------------------

  document.getElementById("console-lock").addEventListener("click", function () {
    post(cfg.lock, {}).catch(function () {}).then(function () {
      window.location.reload();
    });
  });

  document.getElementById("console-new").addEventListener("click", function () {
    if (shellAlive && !window.confirm("Fermer le shell en cours et en ouvrir un neuf ?")) return;
    post(cfg.close, {}).catch(function () {}).then(function () {
      window.location.reload();
    });
  });

  setStatus("connexion…", "warn");
  readLoop();
})();
