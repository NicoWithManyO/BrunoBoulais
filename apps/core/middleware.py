"""Lightweight visitor counter middleware.

Counts unique (date, ip_hash) tuples for public pages — feeds the footer.
Skips: gestion, statics, non-200, non-GET, non-HTML, obvious bots, DEBUG mode.
"""

import hashlib
import ipaddress

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError
from django.utils import timezone

from apps.core.models import VisiteJournaliere

_SKIP_PREFIXES = ("/gestion/", "/static/", "/media/", "/__debug__/", "/accounts/")
_SKIP_PATHS = {"/favicon.ico", "/sitemap.xml", "/robots.txt", "/site.webmanifest"}
_BOT_HINTS = ("bot", "crawl", "spider", "facebookexternalhit", "preview", "monitor", "wget", "curl/")

# En prod : Cloudflare → nginx local → gunicorn. nginx tournant sur le
# même hôte, REMOTE_ADDR vu par gunicorn est soit loopback (bind TCP
# 127.0.0.1) soit "" (bind socket unix — pas de source IP TCP). Les deux
# cas sont implicitement trustés : ni le socket unix ni un port loopback
# ne sont joignables depuis le réseau public, donc seul nginx local peut
# poser CF-Connecting-IP côté requête entrante. /32 (et pas /8) — seul
# 127.0.0.1 est le hop attendu ; un autre process loopback ne doit pas
# pouvoir spoofer. Si un jour gunicorn change de bind (LAN, public, autre
# hôte), réintroduire ici les ranges Cloudflare officiels
# (https://www.cloudflare.com/ips-v4 / -v6) et retirer le cas "" trusté
# dans `_client_ip`.
#
# Précondition critique côté ops : nginx DOIT strip tout CF-Connecting-IP
# entrant côté public (`proxy_set_header CF-Connecting-IP "";` dans le
# bloc location), sinon le trust de REMOTE_ADDR vide ouvre un spoof
# trivial via bypass DNS. Voir to-prod.md.
_TRUSTED_PROXY_NETWORKS = (
    ipaddress.ip_network("127.0.0.1/32"),
    ipaddress.ip_network("::1/128"),
)


def _normalize_ip(ip_str: str) -> str:
    """Forme canonique d'une string IP, "" si vide ou invalide.

    Normalise IPv4-mapped IPv6 (``::ffff:a.b.c.d``) en IPv4 (``a.b.c.d``)
    pour que (a) le check de trust loopback fonctionne sous gunicorn
    dual-stack (sinon ``::ffff:127.0.0.1`` n'est dans aucun range trusté)
    et (b) bucket rate-limit + hash compteur ne collapsent pas toutes
    les IPv4 d'un attaquant dans un bucket unique (le mask /64 sur
    ``::ffff:x.x.x.x`` retombe systématiquement sur ``::``).
    """
    if not ip_str:
        return ""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return ""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return str(ip)


def _is_trusted_proxy(ip_str: str) -> bool:
    if not ip_str:
        return False
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in net for net in _TRUSTED_PROXY_NETWORKS)


def _client_ip(request) -> str:
    """IP réelle du client, normalisée (IPv4-mapped IPv6 → IPv4).

    En prod : Cloudflare → nginx local → gunicorn. Deux cas de bind possibles :
    - TCP loopback (``--bind 127.0.0.1:port``) : REMOTE_ADDR == ``127.0.0.1``,
      trusté par ``_TRUSTED_PROXY_NETWORKS``.
    - Socket unix (``--bind unix:/run/...``) : pas de source IP TCP, donc
      REMOTE_ADDR == ``""``. Le socket n'étant joignable que depuis le host,
      on trust implicitement (seul nginx local peut poser le header).

    Dans les deux cas trustés, on lit ``CF-Connecting-IP`` (positionné par
    Cloudflare et écrasé sur chaque hop CF). Si la requête arrive d'ailleurs
    (REMOTE_ADDR == IP publique, cas anormal), on ignore le header pour
    empêcher le spoof.

    Précondition critique côté ops : nginx DOIT strip tout
    ``CF-Connecting-IP`` entrant côté public, sinon le trust REMOTE_ADDR==""
    ouvre un spoof trivial via bypass DNS. Voir note dans
    ``_TRUSTED_PROXY_NETWORKS`` + to-prod.md.

    Toute valeur lue (REMOTE_ADDR ou CF-Connecting-IP) passe par
    ``_normalize_ip`` : invalide / comma-list / junk → traité comme
    absent et on retombe sur la source précédente. Les callers
    (``_ratelimit_bucket``, compteur de visites) peuvent supposer que
    le retour est soit ``""`` soit une string IP canoniquement parseable.

    Trust gate : on check la valeur RAW de REMOTE_ADDR pour le cas socket
    unix (``== ""``), pas la valeur normalisée. ``_normalize_ip`` swallow
    les ``ValueError`` en retournant ``""`` — sur la valeur normalisée
    seule, un REMOTE_ADDR non-vide mais malformé (whitespace, garbage,
    XFF-style comma-list) collapserait sur ``""`` et hériterait du trust
    socket unix. Gater sur la raw garde ça strict : seul un REMOTE_ADDR
    réellement absent compte comme socket unix.
    """
    remote_raw = request.META.get("REMOTE_ADDR", "")
    remote = _normalize_ip(remote_raw)
    trusted = remote_raw == "" or _is_trusted_proxy(remote)
    if trusted:
        cf_ip = _normalize_ip(request.META.get("HTTP_CF_CONNECTING_IP", "").strip())
        if cf_ip:
            return cf_ip
    return remote


def _is_bot(user_agent: str) -> bool:
    ua = user_agent.lower()
    return any(hint in ua for hint in _BOT_HINTS)


class VisiteurCompteurMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if settings.DEBUG:
            return response
        if request.method != "GET" or response.status_code != 200:
            return response
        if not response.get("Content-Type", "").startswith("text/html"):
            return response

        path = request.path
        if path in _SKIP_PATHS or any(path.startswith(p) for p in _SKIP_PREFIXES):
            return response

        user_agent = request.META.get("HTTP_USER_AGENT", "")
        if _is_bot(user_agent):
            return response

        ip = _client_ip(request)
        if not ip:
            return response

        today = timezone.localdate()
        raw = f"{settings.SECRET_KEY}|{today.isoformat()}|{ip}|{user_agent}"
        ip_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        # Évite un SELECT par pageview pour les visiteurs déjà comptés
        # aujourd'hui sur ce worker. TTL 24 h.
        seen_key = f"vu:{today.isoformat()}:{ip_hash}"
        if cache.get(seen_key):
            return response

        try:
            VisiteJournaliere.objects.get_or_create(date=today, ip_hash=ip_hash)
        except DatabaseError:
            # Compteur best-effort, ne jamais casser la réponse.
            return response

        cache.set(seen_key, True, 86400)
        return response
