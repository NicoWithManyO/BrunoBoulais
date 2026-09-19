# Console shell HTTPS — mise en prod

Une page du site qui ouvre un vrai terminal sur le serveur, **en HTTPS
uniquement**. Pas de WebSocket, pas de port en plus : uniquement des `POST`
JSON vers le domaine du site. C'est ce qui permet d'administrer le serveur
depuis un réseau qui ferme le port 22 (et qui filtre souvent l'upgrade
WebSocket dans la foulée).

Code : `apps/console/` — `views.py` (auth + relais), `daemon.py` (le PTY),
`client.py` (lancement du démon), `theme/static/js/console.js` (terminal),
xterm.js auto-hébergé dans `static/vendor/xterm/`.

## Activation

Par défaut, **rien n'est exposé** : l'URL n'est même pas branchée dans le
urlconf. Pour l'activer, dans le `.env` de prod :

```ini
CONSOLE_ENABLED=True
CONSOLE_TOKEN=<secret long>          # obligatoire, sinon la console reste morte
CONSOLE_URL_PATH=atelier-xyz/        # autre chose que "console/"
CONSOLE_USERS=nico                   # facultatif, en plus du filtre superuser
```

Générer le token :

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Puis redémarrer gunicorn. La page est à `https://<domaine>/<CONSOLE_URL_PATH>`.

Pour couper : `CONSOLE_ENABLED=False` + redémarrage. Pour révoquer un accès
sans couper : changer `CONSOLE_TOKEN` (les sessions déverrouillées le restent
jusqu'au prochain verrouillage — ajouter un `CONSOLE_USERS` ou changer le mot
de passe du compte si c'est urgent).

## Ce qui protège la page

| Garde-fou | Effet |
|---|---|
| `CONSOLE_ENABLED` (défaut False) | URL absente du urlconf |
| `CONSOLE_TOKEN` vide | 404, même activée |
| superuser requis (+ `CONSOLE_USERS`) | 404 pour tous les autres, Bruno compris |
| mot de passe **et** token à re-saisir | un cookie de session volé ne donne pas de shell |
| verrouillage auto (`CONSOLE_UNLOCK_TTL`, 30 min glissantes) | onglet oublié = verrouillé |
| rate-limit 10 tentatives/heure/IP | pas de brute-force du token |
| `Cache-Control: no-store` + `X-Robots-Tag: noindex` | rien en cache, rien indexé |
| shell coupé après 30 min d'inactivité / 12 h max | pas de bash orphelin |

À garder en tête : un shell ici, c'est **les droits de l'utilisateur qui fait
tourner le site** — donc le `.env`, la base, les clés Stripe. Le token est la
dernière barrière ; il ne vit que dans le `.env`, jamais dans le dépôt.

Toutes les ouvertures, fermetures et tentatives ratées partent dans les logs
applicatifs (`apps.console.views`) — visibles avec `journalctl -u <service>`.
Chaque session a aussi son log technique dans `CONSOLE_RUNTIME_DIR`.

## Côté serveur

**Sockets.** Les démons PTY communiquent par socket unix dans
`CONSOLE_RUNTIME_DIR` (défaut : `<projet>/.console/`, créé en 0700, ignoré par
git). Rien n'y est servi par le web. Si le projet est sur un montage `noexec`
ou en lecture seule, pointer la variable vers `/run/<service>/console`.

**systemd.** Le démon est détaché (`start_new_session`) : il survit au
recyclage des workers gunicorn. Il ne survit pas à un `systemctl restart` si
l'unité est en `KillMode=control-group` (le défaut) — le cgroup emporte tout.
Pour garder son shell ouvert à travers un redémarrage du site :

```ini
[Service]
KillMode=mixed
```

Sans ça, ce n'est pas grave : on recharge la page, une nouvelle session
s'ouvre. Mais une commande longue lancée depuis la console est coupée.

**nginx / Cloudflare.** Rien de spécial : ce sont des POST courts vers le même
domaine. Pas de `proxy_read_timeout` à rallonger, pas de `Upgrade` à passer.
Le rate-limit s'appuie sur l'IP réelle, donc sur `CF-Connecting-IP` comme le
reste du site (cf. `apps/core/middleware.py`) : si le site est joint en
contournant Cloudflare, la console se refuse (fail closed).

**Locale.** Si le process web n'a pas de locale UTF-8, le shell en reçoit une
(`CONSOLE_LOCALE`, défaut `C.UTF-8`). Mettre `fr_FR.UTF-8` si elle est générée
sur le serveur (`locale -a`).

## Rythme des requêtes

gunicorn tourne à **un seul worker** (contrainte du rate-limit, cf.
`apps/core/ratelimit.py`). Le terminal fait donc du *polling* adaptatif —
~8 requêtes/s pendant la frappe, une toutes les 2 s au repos, une toutes les
5 s en arrière-plan — et le serveur répond immédiatement sans jamais attendre
(`CONSOLE_POLL_WAIT=0`). Chaque requête est minuscule (quelques centaines
d'octets), mais elle occupe l'unique worker le temps d'un aller-retour.

Si un jour gunicorn passe à plusieurs workers ou à des threads
(`--threads 4`), monter `CONSOLE_POLL_WAIT=1.5` : le serveur garde alors la
requête ouverte jusqu'à ce qu'il y ait de la sortie, ce qui divise le nombre
de requêtes par ~20 et rend l'affichage plus nerveux. **Ne pas le faire avec
un worker unique** : la requête bloquerait tout le site pendant l'attente.

## Vérifier que ça marche

1. Se connecter à `/gestion/`, puis aller sur l'URL de la console.
2. Mot de passe + token → le terminal doit afficher un prompt en une seconde.
3. `echo $TERM` → `xterm-256color` ; `tput cols` doit suivre la taille de la
   fenêtre ; `vi` doit s'afficher correctement (c'est un vrai PTY).
4. Recharger la page : on retombe sur la **même** session, avec son historique.
5. « Verrouiller » → on doit redemander mot de passe et token.

## Limites connues

- Un seul shell à la fois par session de navigateur. Pour plusieurs
  terminaux, utiliser `tmux` dedans (c'est d'ailleurs conseillé : `tmux a ||
  tmux` en arrivant, et plus rien ne se perd).
- Les frappes envoyées pendant une coupure réseau sont perdues (jamais
  rejouées à l'aveugle) ; la sortie, elle, est rattrapée intégralement tant
  que le démon vit.
- Le scrollback côté serveur est de 512 Ko : au-delà d'une coupure longue avec
  beaucoup de sortie, le terminal se redessine sur ce qui reste.
