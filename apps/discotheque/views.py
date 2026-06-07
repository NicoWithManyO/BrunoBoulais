from django.shortcuts import render

from apps.core.seo import seo

from .models import Chanson, DiscothequePage


def liste(request):
    chansons = Chanson.objects.filter(publie=True)
    has_enregistrements = chansons.filter(type=Chanson.TYPE_ENREGISTREMENT).exists()
    return render(
        request,
        "discotheque/liste.html",
        {
            "chansons": chansons,
            "has_enregistrements": has_enregistrements,
            "page": DiscothequePage.get_solo(),
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
