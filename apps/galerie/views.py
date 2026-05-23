from django.shortcuts import render

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
        },
    )
