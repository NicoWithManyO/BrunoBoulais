"""Lightweight visitor counter middleware.

Counts unique (date, ip_hash) tuples for public pages — feeds the footer.
Skips: gestion, statics, non-200, non-GET, non-HTML, obvious bots, DEBUG mode.
"""

import hashlib
from datetime import date as date_cls

from django.conf import settings
from django.db import DatabaseError

from apps.core.models import VisiteJournaliere

_SKIP_PREFIXES = ("/gestion/", "/static/", "/media/", "/__debug__/", "/accounts/")
_SKIP_PATHS = {"/favicon.ico", "/sitemap.xml", "/robots.txt", "/site.webmanifest"}
_BOT_HINTS = ("bot", "crawl", "spider", "facebookexternalhit", "preview", "monitor", "wget", "curl/")


def _client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


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

        today = date_cls.today()
        raw = f"{settings.SECRET_KEY}|{today.isoformat()}|{ip}|{user_agent}"
        ip_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        try:
            VisiteJournaliere.objects.get_or_create(date=today, ip_hash=ip_hash)
        except DatabaseError:
            # Compteur best-effort, ne jamais casser la réponse.
            pass

        return response
