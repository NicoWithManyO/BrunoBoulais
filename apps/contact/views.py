import ipaddress
import logging
import math

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse
from django_ratelimit.core import get_usage

from apps.core.middleware import _client_ip
from apps.core.seo import seo

from .forms import CommandeForm
from .models import (
    FRAIS_PORT_CENTS,
    PRIX_LIVRE_CENTS,
    ContactPage,
    Message,
    montant_detail,
)

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


def commande(request):
    rate_limited = False
    ip_unresolved = False
    retry_after = None
    if request.method == "POST":
        form = CommandeForm(request.POST)
        # Honeypot trip = bot. On burn le bucket (pénaliser) puis on redirect
        # /merci/ pour ne pas révéler qu'on a détecté le piège (anti-fingerprint).
        if (request.POST.get("website") or "").strip():
            bucket = _ratelimit_bucket(request)
            if bucket is None:
                _log_ip_unresolved_dedup(request)
            else:
                _bucket_usage(request, bucket, increment=True)
            # Purge d'une éventuelle commande résiduelle : le piège ne doit pas
            # réafficher le récap d'une commande précédente sur /merci/.
            request.session.pop("order_ref", None)
            return redirect(reverse("contact:merci"))
        if form.is_valid():
            bucket = _ratelimit_bucket(request)
            if bucket is None:
                _log_ip_unresolved_dedup(request)
                ip_unresolved = True
            else:
                usage = _bucket_usage(request, bucket, increment=False)
                if usage is not None and usage["count"] >= usage["limit"]:
                    rate_limited = True
                    retry_after = max(1, math.ceil(usage["time_left"]))
                else:
                    msg = form.save_and_notify()
                    _bucket_usage(request, bucket, increment=True)
                    # Référence conservée pour afficher le récap + la consigne de
                    # paiement sur /merci/ (mode/quantité relus depuis le Message).
                    if msg.sujet == Message.SUJET_COMMANDE and msg.mode_paiement:
                        request.session["order_ref"] = msg.pk
                    else:
                        request.session.pop("order_ref", None)
                    return redirect(reverse("contact:merci"))
    else:
        form = CommandeForm()
    response = render(
        request,
        "contact/commande.html",
        {
            "form": form,
            "page": ContactPage.get_solo(),
            "commande_value": Message.SUJET_COMMANDE,
            "paiement_cheque": Message.PAIEMENT_CHEQUE,
            "paiement_virement": Message.PAIEMENT_VIREMENT,
            "livraison_domicile": Message.LIVRAISON_DOMICILE,
            "mondial_relay_brand": settings.MONDIAL_RELAY_BRAND,
            # Tarifs pour le récap calculé côté navigateur (source = centimes Python).
            "tarifs": {
                "prixLivreCents": PRIX_LIVRE_CENTS,
                "fraisPortCents": {
                    f"{nb}|{mode}": cents for (nb, mode), cents in FRAIS_PORT_CENTS.items()
                },
            },
            "rate_limited": rate_limited,
            "ip_unresolved": ip_unresolved,
            **seo(
                request,
                title="Contact & commande · Bruno Boulais",
                description="Commander le livre ou écrire à Bruno Boulais.",
            ),
        },
    )
    if ip_unresolved:
        response.status_code = 503
        response["Cache-Control"] = "no-store"
    elif rate_limited:
        response.status_code = 429
        response["Retry-After"] = str(retry_after)
        response["Cache-Control"] = "no-store"
    return response


def commande_merci(request):
    # Référence lue une seule fois (consigne de paiement affichée au retour du
    # formulaire) : un rechargement retombe sur le simple remerciement.
    ref = request.session.pop("order_ref", None)
    order = Message.objects.filter(pk=ref).first() if ref else None
    detail = montant_detail(order.nb_exemplaires, order.mode_livraison) if order else None
    return render(
        request,
        "contact/commande_merci.html",
        {
            "page": ContactPage.get_solo(),
            "order": order,
            "montant": detail["total"] if detail else "",
            "paiement_cheque": Message.PAIEMENT_CHEQUE,
            "paiement_virement": Message.PAIEMENT_VIREMENT,
            **seo(request, title="Message envoyé · Bruno Boulais"),
        },
    )
