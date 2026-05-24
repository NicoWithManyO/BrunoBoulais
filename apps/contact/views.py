import ipaddress
import logging

from django.shortcuts import redirect, render
from django.urls import reverse
from django_ratelimit.core import is_ratelimited

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
    (un /64 résidentiel donne 2^64 adresses sinon).

    Retourne ``None`` si l'IP est absente ou syntaxiquement invalide (cas
    d'un CF-Connecting-IP spoofé avec une string bidon) — le caller doit
    fail closed dans ce cas.
    """
    ip = _client_ip(request)
    if not ip:
        return None
    try:
        mask = 64 if ":" in ip else 32
        return str(ipaddress.ip_network(f"{ip}/{mask}", strict=False).network_address)
    except ValueError:
        return None


def contact(request):
    rate_limited = False
    if request.method == "POST":
        form = ContactForm(request.POST)
        # Le rate-limit n'est consommé QUE si le form est valide — un user qui
        # se rate sur ses champs ne brûle pas son quota. Si le bucket IP est
        # introuvable (IP vide / spoof bidon), on bloque par défaut.
        if form.is_valid():
            bucket = _ratelimit_bucket(request)
            if bucket is None:
                logger.error(
                    "Contact: IP client indéterminée, POST bloqué (path=%s)",
                    request.path,
                )
                rate_limited = True
            else:
                rate_limited = is_ratelimited(
                    request=request,
                    group="contact:contact",
                    key=lambda g, r: bucket,
                    rate="5/h",
                    method="POST",
                    increment=True,
                )
                if not rate_limited:
                    form.save_and_notify()
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
