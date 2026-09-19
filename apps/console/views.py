"""Console web : un shell sur le serveur, servi en HTTPS ordinaire.

Raison d'être : depuis certains réseaux d'entreprise, le port 22 est fermé —
SSH est inatteignable. Ici tout passe par des requêtes POST HTTPS vers le même
domaine que le site, donc ça traverse n'importe quel proxy d'entreprise, sans
WebSocket (souvent filtré lui aussi) et sans port supplémentaire à ouvrir.

Garde-fous — une page qui donne un shell root-ish mérite d'être paranoïaque :

1. ``CONSOLE_ENABLED`` à False par défaut : sur une install qui ne l'active
   pas, l'URL n'existe même pas (le urlconf ne la branche pas).
2. ``CONSOLE_TOKEN`` obligatoire : sans secret posé dans l'environnement, la
   console refuse de servir, même activée.
3. Deux facteurs : être connecté en superuser NE SUFFIT PAS. Il faut
   re-saisir son mot de passe *et* le token, comme le « sudo mode » de
   l'admin. Un cookie de session volé ne donne donc pas de shell.
4. 404 (et pas 403) pour tout le monde d'autre, Bruno compris : rien ne
   signale l'existence de la page.
5. Déverrouillage glissant (``CONSOLE_UNLOCK_TTL``), rate-limit sur les
   tentatives, et journalisation de toutes les ouvertures/fermetures.

Le PTY lui-même vit dans un process détaché (cf. daemon.py) : il survit au
recyclage des workers gunicorn, et le worker web ne fait que relayer des
octets.
"""

from __future__ import annotations

import base64
import binascii
import getpass
import json
import logging
import math
import time
from functools import wraps

from django.conf import settings
from django.contrib.auth import authenticate
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.crypto import constant_time_compare
from django.views.decorators.http import require_POST

from apps.core.middleware import _client_ip
from apps.core.ratelimit import bucket_usage, log_ip_unresolved_dedup, ratelimit_bucket

from . import client

logger = logging.getLogger(__name__)

# Rate-limit des tentatives de déverrouillage (bucket IP partagé du projet).
_RL_GROUP = "console:unlock"
_RL_RATE = "10/h"
_RL_LOG_KEY = "apps.console.views:ip-unresolved-logged"

SESSION_SID = "console_sid"
SESSION_UNLOCKED = "console_unlocked_at"

# Cap sur les octets envoyés au PTY en une requête (un gros coller reste
# largement dessous ; au-delà c'est du remplissage de buffer).
INPUT_MAX = 256 * 1024


def is_configured() -> bool:
    """La console n'est servie qu'activée ET avec un token posé."""
    if not settings.CONSOLE_ENABLED:
        return False
    if not settings.CONSOLE_TOKEN:
        logger.error("CONSOLE_ENABLED=True mais CONSOLE_TOKEN vide : console désactivée.")
        return False
    return True


def is_allowed(user) -> bool:
    if not (user.is_authenticated and user.is_active and user.is_superuser):
        return False
    allowlist = settings.CONSOLE_USERS
    return not allowlist or user.get_username() in allowlist


def console_required(view_func):
    """Connecté + superuser (+ allowlist). 404 pour tous les autres."""

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not is_configured():
            raise Http404
        if not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")
        if not is_allowed(request.user):
            logger.warning(
                "Console: accès refusé pour %s (ip=%s)",
                request.user.get_username(),
                _client_ip(request) or "?",
            )
            raise Http404
        response = view_func(request, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response

    return wrapped


def _unlocked(request) -> bool:
    """Déverrouillage valide ? TTL glissant, rafraîchi à chaque échange."""
    since = request.session.get(SESSION_UNLOCKED)
    if not isinstance(since, (int, float)):
        return False
    return (time.time() - since) < settings.CONSOLE_UNLOCK_TTL


def _touch_unlock(request):
    request.session[SESSION_UNLOCKED] = time.time()
    # Sans ça, Django ne réécrit pas le cookie de session à chaque requête et
    # la fenêtre glissante ne glisse pas.
    request.session.modified = True


def _lock(request):
    request.session.pop(SESSION_UNLOCKED, None)
    request.session.modified = True


# --- page -------------------------------------------------------------------


@console_required
def console(request):
    """Formulaire de déverrouillage, puis le terminal."""
    error = None
    retry_after = None

    if request.method == "POST":
        bucket = ratelimit_bucket(request)
        if bucket is None:
            # Fail closed : sans IP identifiable, pas de rate-limit possible,
            # donc pas de console.
            log_ip_unresolved_dedup(request, log_key=_RL_LOG_KEY, label="Console")
            error = "Impossible d'identifier la requête. Réessayer depuis le réseau habituel."
        else:
            usage = bucket_usage(request, bucket, group=_RL_GROUP, rate=_RL_RATE, increment=False)
            if usage is not None and usage["count"] >= usage["limit"]:
                retry_after = max(1, math.ceil(usage["time_left"]))
                error = "Trop de tentatives. Réessayer plus tard."
            elif _check_credentials(request):
                _touch_unlock(request)
                logger.info(
                    "Console: déverrouillée par %s (ip=%s)",
                    request.user.get_username(),
                    _client_ip(request) or "?",
                )
                return redirect(reverse("console:console"))
            else:
                bucket_usage(request, bucket, group=_RL_GROUP, rate=_RL_RATE, increment=True)
                logger.warning(
                    "Console: déverrouillage refusé pour %s (ip=%s)",
                    request.user.get_username(),
                    _client_ip(request) or "?",
                )
                error = "Mot de passe ou jeton invalide."

    if not _unlocked(request):
        response = render(
            request,
            "console/unlock.html",
            {"error": error, "retry_after": retry_after},
        )
        if retry_after:
            response.status_code = 429
            response["Retry-After"] = str(retry_after)
        return response

    return render(
        request,
        "console/terminal.html",
        {
            "host": settings.SITE_DOMAIN,
            "shell_user": _shell_user(),
            "idle_minutes": int(settings.CONSOLE_UNLOCK_TTL // 60),
            "config": {
                "io": reverse("console:io"),
                "close": reverse("console:close"),
                "lock": reverse("console:lock"),
                # Jeton CSRF posé explicitement : la page est en no-store et
                # fetch() ne lit pas le cookie à notre place.
                "csrf": get_token(request),
                "wait": settings.CONSOLE_POLL_WAIT,
            },
        },
    )


def _check_credentials(request) -> bool:
    """Mot de passe du compte + token serveur, en temps constant côté token."""
    password = request.POST.get("password") or ""
    token = request.POST.get("token") or ""
    if not constant_time_compare(token, settings.CONSOLE_TOKEN):
        return False
    # `authenticate` plutôt que `check_password` : ça passe par les backends
    # configurés et ça applique le durcissement (hashers, comptes inactifs).
    user = authenticate(
        request,
        username=request.user.get_username(),
        password=password,
    )
    return user is not None and user.pk == request.user.pk


def _shell_user() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 — pas d'utilisateur système résolvable (conteneur nu)
        return "?"


# --- API --------------------------------------------------------------------


def _api(view_func):
    """Comme console_required, mais en JSON (le terminal parle en fetch)."""

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not is_configured() or not is_allowed(request.user):
            raise Http404
        if not _unlocked(request):
            return JsonResponse({"error": "locked"}, status=403)
        _touch_unlock(request)
        response = view_func(request, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    return wrapped


def _payload(request) -> dict:
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


@require_POST
@_api
def api_io(request):
    """Envoi de frappes et/ou lecture de la sortie depuis l'offset ``since``.

    Un seul endpoint pour les deux sens : le terminal fait tourner une boucle
    de lecture (``since`` = offset courant) et poste les frappes à côté avec
    ``since: false`` (écriture seule — l'écho revient par la boucle).
    """
    data = _payload(request)
    sid = request.session.get(SESSION_SID)
    fresh = not sid

    if fresh:
        sid = client.new_sid()
        request.session[SESSION_SID] = sid
        request.session.modified = True

    try:
        if fresh or data.get("open"):
            client.ensure(sid)
            if fresh:
                logger.info(
                    "Console: session %s ouverte par %s (ip=%s)",
                    sid,
                    request.user.get_username(),
                    _client_ip(request) or "?",
                )
        payload = client.io(
            sid,
            data=_decode_input(data.get("in")),
            since=data.get("since"),
            wait=min(float(data.get("wait") or 0.0), settings.CONSOLE_POLL_WAIT),
            cols=data.get("cols"),
            rows=data.get("rows"),
        )
    except client.ConsoleError as exc:
        # Session perdue (démon expiré, serveur redémarré…) : on oublie le sid,
        # le prochain appel en ouvrira une neuve.
        request.session.pop(SESSION_SID, None)
        request.session.modified = True
        return JsonResponse({"error": "gone", "detail": str(exc)}, status=409)
    except (ValueError, TypeError) as exc:
        return JsonResponse({"error": "bad-request", "detail": str(exc)}, status=400)

    payload["sid"] = sid
    return JsonResponse(payload)


def _decode_input(raw) -> bytes:
    if not raw:
        return b""
    if not isinstance(raw, str) or len(raw) > INPUT_MAX:
        raise ValueError("entrée invalide")
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("entrée non base64") from exc


@require_POST
@_api
def api_close(request):
    """Ferme le shell (et donc le démon) sans toucher à la session Django."""
    sid = request.session.pop(SESSION_SID, None)
    request.session.modified = True
    if sid:
        client.kill(sid)
        logger.info("Console: session %s fermée par %s", sid, request.user.get_username())
    return JsonResponse({"ok": True})


@require_POST
@console_required
def api_lock(request):
    """Reverrouille : il faudra re-saisir mot de passe + token."""
    if not _unlocked(request):
        return HttpResponseForbidden()
    _lock(request)
    return JsonResponse({"ok": True})
