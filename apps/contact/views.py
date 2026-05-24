from django.shortcuts import redirect, render
from django.urls import reverse
from django_ratelimit.core import is_ratelimited

from apps.core.middleware import _client_ip
from apps.core.seo import seo

from .forms import ContactForm
from .models import ContactPage, Message


def _ratelimit_key(group, request):
    """Clé de rate-limit basée sur l'IP client réelle (CF-Connecting-IP en prod)."""
    return _client_ip(request) or "anon"


def contact(request):
    limited = False
    if request.method == "POST":
        # On vérifie le rate-limit AVANT de toucher au form pour court-circuiter
        # le travail (et éviter d'envoyer un email même si la validation passait).
        # 5 POST par heure et par IP.
        limited = is_ratelimited(
            request=request,
            group="contact:contact",
            key=_ratelimit_key,
            rate="5/h",
            method="POST",
            increment=True,
        )
        form = ContactForm(request.POST)
        if not limited and form.is_valid():
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
            "rate_limited": limited,
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
