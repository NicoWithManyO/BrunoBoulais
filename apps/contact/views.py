import ipaddress
import logging
import math

from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse
from django_ratelimit.core import get_usage

from apps.core.middleware import _client_ip
from apps.core.seo import seo

from .forms import ContactForm
from .models import ContactPage, Message

logger = logging.getLogger(__name__)

# Rate-limit : 5 POST/heure par bucket IP.
# Implémentation : cache LocMem par défaut (per-worker). Pour que la limite
# soit respectée, gunicorn doit tourner avec UN seul worker. Sinon le cap
# effectif devient 5/h × N workers. Switch vers Redis si on a besoin de scaler.


def _ratelimit_bucket(request):
    """Bucket de rate-limit : IP client masquée /32 (IPv4) ou /64 (IPv6).

    IPv6 est masqué à /64 pour empêcher la rotation des bits bas
    (un /64 résidentiel donne 2^64 adresses sinon). IPv4-mapped IPv6
    a déjà été normalisé en IPv4 par ``_client_ip`` (sinon le mask /64
    sur ``::ffff:x.x.x.x`` retombe sur ``::`` et tous les attaquants
    partagent un bucket unique).

    Retourne ``None`` si l'IP est absente — le caller doit fail closed
    dans ce cas. La string retournée par ``_client_ip`` est garantie
    canoniquement parseable (cf docstring), donc pas de try/except ici.
    """
    ip_str = _client_ip(request)
    if not ip_str:
        return None
    ip = ipaddress.ip_address(ip_str)
    mask = 32 if isinstance(ip, ipaddress.IPv4Address) else 64
    return str(ipaddress.ip_network(f"{ip}/{mask}", strict=False).network_address)


def _bucket_usage(request, bucket, *, increment):
    """Wrapper get_usage avec config view-spécifique (5/h, group).

    ``increment=False`` lit le compteur sans bump (gating pré-save).
    ``increment=True`` bump (post-save success, ou honeypot trip).

    Retourne le dict {count, limit, should_limit, time_left} ou ``None``
    si le rate-limit est désactivé / non applicable. Le caller compare
    ``count >= limit`` (NB : ``should_limit = count > limit`` côté
    django-ratelimit, donc pas utilisable avec le pattern check-then-bump
    sans off-by-one).
    """
    return get_usage(
        request=request,
        group="contact:contact",
        key=lambda g, r: bucket,
        rate="5/h",
        method="POST",
        increment=increment,
    )


def _log_ip_unresolved_dedup(request):
    """Log warning IP indéterminée, dédupliqué 5 min via cache.

    Sans dédup, chaque POST sur ce path part en Sentry/PagerDuty : un
    attaquant qui force REMOTE_ADDR vide peut spam la pile d'alerting.
    Clé courte (pas par path) car on a une seule vue concernée.
    """
    # Clé namespacée par module pour éviter une collision si un autre helper
    # (tests, autre vue) réutilise le préfixe "contact:" dans le futur.
    log_key = "apps.contact.views:ip-unresolved-logged"
    if cache.add(log_key, True, 300):
        # %r (repr) échappe CR/LF dans request.path — Django décode les
        # %-encoded chars de l'URL, donc %0A devient un newline littéral
        # qui injecterait une fausse ligne dans la sortie console/SIEM.
        logger.warning(
            "Contact: IP client indéterminée, POST bloqué (path=%r)",
            request.path,
        )


def contact(request):
    rate_limited = False
    ip_unresolved = False
    retry_after = None
    if request.method == "POST":
        form = ContactForm(request.POST)
        # Honeypot trip = bot. On burn le bucket (pénaliser) puis on
        # redirect /merci/ pour ne pas révéler qu'on a détecté le piège
        # (anti-fingerprint). Check sur request.POST brut pour éviter de
        # déclencher form.full_clean() avant la décision.
        if (request.POST.get("website") or "").strip():
            bucket = _ratelimit_bucket(request)
            if bucket is None:
                # Même path forensique que la branche fail-closed : un bot
                # qui combine honeypot trip + IP strippée doit laisser une
                # trace (dédupliquée), sinon il passe sous radar.
                _log_ip_unresolved_dedup(request)
            else:
                _bucket_usage(request, bucket, increment=True)
            return redirect(reverse("contact:merci"))
        # Vraie validation : champs requis, cohérence commande, etc. Le
        # quota n'est PAS consommé sur erreur de validation (typo user)
        # ni sur fail save (DB/email transitoire) — uniquement sur
        # succès complet (bump après save_and_notify).
        if form.is_valid():
            bucket = _ratelimit_bucket(request)
            if bucket is None:
                # Fail closed : on ne peut pas bucket-er, on bloque. Pas de
                # Retry-After (attendre ne résout pas une IP absente) et
                # 503 plutôt que 429 (ce n'est pas une rate limit, c'est
                # une indisponibilité).
                _log_ip_unresolved_dedup(request)
                ip_unresolved = True
            else:
                usage = _bucket_usage(request, bucket, increment=False)
                if usage is not None and usage["count"] >= usage["limit"]:
                    rate_limited = True
                    # max(1, ceil(...)) borne Retry-After à ≥ 1s :
                    # - boundary (time_left=0, requête pile au tick de reset)
                    #   sans floor donne "Retry-After: 0" = retry immédiat ;
                    # - sentinel cache-fail de django-ratelimit (time_left=-1
                    #   quand count=0/limit=0/should_limit=True) donnerait un
                    #   Retry-After négatif, invalide RFC 7231.
                    retry_after = max(1, math.ceil(usage["time_left"]))
                else:
                    form.save_and_notify()
                    _bucket_usage(request, bucket, increment=True)
                    return redirect(reverse("contact:merci"))
    else:
        form = ContactForm()
    response = render(
        request,
        "contact/form.html",
        {
            "form": form,
            "page": ContactPage.get_solo(),
            "commande_value": Message.SUJET_COMMANDE,
            "rate_limited": rate_limited,
            "ip_unresolved": ip_unresolved,
            **seo(
                request,
                title="Contact & commande dédicacée · Bruno Boulais",
                description=(
                    "Commander le livre avec une dédicace personnalisée ou écrire"
                    " à Bruno Boulais."
                ),
            ),
        },
    )
    # Priorité ip_unresolved > rate_limited : fail-closed (503) prime sur
    # rate-limit (429) si un refactor futur rend les deux flags True en
    # même temps. Aujourd'hui ils s'excluent par control flow, mais on
    # cadre la priorité pour ne pas dépendre de cet invariant implicite.
    if ip_unresolved:
        # 503 sans Retry-After (attendre ne résout pas l'IP absente) + no-store
        # pour empêcher Cloudflare/CDN de cacher l'erreur au edge (RFC 7234 :
        # 503 est cacheable par heuristique sans Cache-Control explicite).
        response.status_code = 503
        response["Cache-Control"] = "no-store"
    elif rate_limited:
        # HTTP 429 + Retry-After : non cacheable par les CDN, et bots/scripts
        # voient l'erreur explicitement (au lieu d'un 200 qui ressemble à un
        # succès et déclenche un re-submit qui ré-incrémente).
        response.status_code = 429
        response["Retry-After"] = str(retry_after)
        response["Cache-Control"] = "no-store"
    return response


def merci(request):
    return render(
        request,
        "contact/merci.html",
        {
            "page": ContactPage.get_solo(),
            **seo(request, title="Message envoyé · Bruno Boulais"),
        },
    )
