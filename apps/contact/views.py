import ipaddress
import logging

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


def contact(request):
    rate_limited = False
    if request.method == "POST":
        form = ContactForm(request.POST)
        # Honeypot trip = bot. On burn le bucket (pénaliser) puis on
        # redirect /merci/ pour ne pas révéler qu'on a détecté le piège
        # (anti-fingerprint). Check sur request.POST brut pour éviter de
        # déclencher form.full_clean() avant la décision.
        if (request.POST.get("website") or "").strip():
            bucket = _ratelimit_bucket(request)
            if bucket is not None:
                _bucket_usage(request, bucket, increment=True)
            return redirect(reverse("contact:merci"))
        # Vraie validation : champs requis, cohérence commande, etc. Le
        # quota n'est PAS consommé sur erreur de validation (typo user)
        # ni sur fail save (DB/email transitoire) — uniquement sur
        # succès complet (bump après save_and_notify).
        if form.is_valid():
            bucket = _ratelimit_bucket(request)
            if bucket is None:
                logger.error(
                    "Contact: IP client indéterminée, POST bloqué (path=%s)",
                    request.path,
                )
                rate_limited = True
            else:
                usage = _bucket_usage(request, bucket, increment=False)
                if usage is not None and usage["count"] >= usage["limit"]:
                    rate_limited = True
                else:
                    form.save_and_notify()
                    _bucket_usage(request, bucket, increment=True)
                    return redirect(reverse("contact:merci"))
    else:
        form = ContactForm()
    return render(
        request,
        "contact/form.html",
        {
            "form": form,
            "page": ContactPage.get_solo(),
            "commande_value": Message.SUJET_COMMANDE,
            "rate_limited": rate_limited,
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


def merci(request):
    return render(
        request,
        "contact/merci.html",
        {
            "page": ContactPage.get_solo(),
            **seo(request, title="Message envoyé · Bruno Boulais"),
        },
    )
