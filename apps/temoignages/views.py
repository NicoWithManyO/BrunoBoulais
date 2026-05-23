from django.shortcuts import render

from apps.core.seo import seo

from .models import Temoignage


def liste(request):
    qs = Temoignage.objects.filter(statut=Temoignage.STATUT_PUBLIE)
    return render(
        request,
        "temoignages/liste.html",
        {
            "temoignages": qs,
            **seo(
                request,
                title="Témoignages de lecteurs · Bruno Boulais",
                description=(
                    "Ce que les lecteurs disent du livre de Bruno Boulais sur"
                    " Jacques Bertin, le géant discret de la chanson."
                ),
            ),
        },
    )
