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

# Ranges IP Cloudflare (téléchargés 2026-05-25 depuis
# https://www.cloudflare.com/ips-v4 et /ips-v6). À ré-actualiser
# ponctuellement — le set évolue très lentement. ``strict=False``
# protège contre un typo avec host bits set (sinon raise à l'import,
# le process ne boote plus).
_TRUSTED_PROXY_NETWORKS = tuple(
    ipaddress.ip_network(n, strict=False) for n in (
        # Loopback : Caddy fait reverse_proxy vers gunicorn sur le même VPS.
        # /32 (et pas /8) — seul 127.0.0.1 est le hop Caddy ; un autre
        # process loopback ne doit pas pouvoir spoofer CF-Connecting-IP.
        "127.0.0.1/32", "::1/128",
        # Cloudflare IPv4
        "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22",
        "103.31.4.0/22", "141.101.64.0/18", "108.162.192.0/18",
        "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22",
        "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
        "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
        # Cloudflare IPv6
        "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32",
        "2405:b500::/32", "2405:8100::/32", "2a06:98c0::/29",
        "2c0f:f248::/32",
    )
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

    En prod : Cloudflare → Caddy (loopback) → gunicorn. REMOTE_ADDR vue
    par gunicorn = 127.0.0.1 (Caddy), donc trusted, donc on lit
    ``CF-Connecting-IP`` (positionné par Cloudflare et écrasé sur chaque
    hop CF). Si la requête arrive d'ailleurs (bypass DNS, sonde directe),
    REMOTE_ADDR n'est pas trusted et on ignore le header pour empêcher
    le spoof. Suppose que Caddy strip tout CF-Connecting-IP entrant côté
    public — voir note ops dans le plan sécu.

    Toute valeur lue (REMOTE_ADDR ou CF-Connecting-IP) passe par
    ``_normalize_ip`` : invalide / comma-list / junk → traité comme
    absent et on retombe sur la source précédente. Les callers
    (``_ratelimit_bucket``, compteur de visites) peuvent supposer que
    le retour est soit ``""`` soit une string IP canoniquement parseable.
    """
    remote = _normalize_ip(request.META.get("REMOTE_ADDR", ""))
    if _is_trusted_proxy(remote):
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
