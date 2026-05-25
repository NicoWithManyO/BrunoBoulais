from django.shortcuts import render

from apps.core.seo import seo

from .models import Chanson


def liste(request):
    chansons = Chanson.objects.filter(publie=True)
    return render(
        request,
        "discotheque/liste.html",
        {
            "chansons": chansons,
            **seo(
                request,
                title="Discothèque · Bruno Boulais",
                description=(
                    "Écoutez les chansons de Jacques Bertin présentées dans"
                    " « Jacques Bertin, le géant discret de la chanson »."
                ),
            ),
        },
    )
