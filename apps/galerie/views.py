from django.shortcuts import render

from apps.core.seo import seo

from .models import Media


def galerie(request):
    categorie = request.GET.get("c") or ""
    qs = Media.objects.filter(publie=True)
    if categorie:
        qs = qs.filter(categorie=categorie)
    return render(
        request,
        "galerie/liste.html",
        {
            "medias": qs,
            "categorie_active": categorie,
            "categories": Media.CATEGORIE_CHOICES,
            **seo(
                request,
                title="Galerie photos · Bruno Boulais",
                description=(
                    "Photos de Jacques Bertin sur scène, des dédicaces de Bruno"
                    " Boulais et des éditions du livre."
                ),
            ),
        },
    )
