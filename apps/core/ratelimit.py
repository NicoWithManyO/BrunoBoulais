"""Rate-limit par bucket IP, partagé entre les vues POST publiques (contact, checkout).

Implémentation : cache LocMem par défaut (per-worker). Pour que la limite soit
respectée, gunicorn doit tourner avec UN seul worker. Sinon le cap effectif
devient ``rate × N workers``. Switch vers Redis si on a besoin de scaler.
"""

import ipaddress
import logging

from django.core.cache import cache
from django_ratelimit.core import get_usage

from apps.core.middleware import _client_ip

logger = logging.getLogger(__name__)


def ratelimit_bucket(request):
    """Bucket de rate-limit : IP client masquée /32 (IPv4) ou /64 (IPv6).

    IPv6 est masqué à /64 pour empêcher la rotation des bits bas (un /64
    résidentiel donne 2^64 adresses sinon). IPv4-mapped IPv6 a déjà été
    normalisé en IPv4 par ``_client_ip`` (sinon le mask /64 sur
    ``::ffff:x.x.x.x`` retombe sur ``::`` et tous les attaquants partagent
    un bucket unique).

    Retourne ``None`` si l'IP est absente — le caller doit fail closed dans
    ce cas. La string retournée par ``_client_ip`` est garantie canoniquement
    parseable (cf docstring), donc pas de try/except ici.
    """
    ip_str = _client_ip(request)
    if not ip_str:
        return None
    ip = ipaddress.ip_address(ip_str)
    mask = 32 if isinstance(ip, ipaddress.IPv4Address) else 64
    return str(ipaddress.ip_network(f"{ip}/{mask}", strict=False).network_address)


def bucket_usage(request, bucket, *, group, rate, increment):
    """Wrapper get_usage avec config view-spécifique (group + rate).

    ``increment=False`` lit le compteur sans bump (gating pré-save).
    ``increment=True`` bump (post-save success, ou honeypot trip).

    Retourne le dict {count, limit, should_limit, time_left} ou ``None`` si le
    rate-limit est désactivé / non applicable. Le caller compare
    ``count >= limit`` (NB : ``should_limit = count > limit`` côté
    django-ratelimit, donc pas utilisable avec le pattern check-then-bump
    sans off-by-one).
    """
    return get_usage(
        request=request,
        group=group,
        key=lambda g, r: bucket,
        rate=rate,
        method="POST",
        increment=increment,
    )


def log_ip_unresolved_dedup(request, *, log_key, label):
    """Log warning IP indéterminée, dédupliqué 5 min via cache.

    Sans dédup, chaque POST sur ce path part en Sentry/PagerDuty : un
    attaquant qui force REMOTE_ADDR vide peut spam la pile d'alerting.
    ``log_key`` namespacé par module appelant pour éviter les collisions.
    """
    if cache.add(log_key, True, 300):
        # %r (repr) échappe CR/LF dans request.path — Django décode les
        # %-encoded chars de l'URL, donc %0A devient un newline littéral
        # qui injecterait une fausse ligne dans la sortie console/SIEM.
        logger.warning(
            "%s: IP client indéterminée, POST bloqué (path=%r)",
            label,
            request.path,
        )
