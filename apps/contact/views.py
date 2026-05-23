from django.shortcuts import redirect, render
from django.urls import reverse

from apps.core.seo import seo

from .forms import ContactForm


def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save_and_notify()
            return redirect(reverse("contact:merci"))
    else:
        form = ContactForm()
    return render(
        request,
        "contact/form.html",
        {
            "form": form,
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
        seo(request, title="Message envoyé · Bruno Boulais"),
    )
