from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from apps.actualites.models import Actualite
from apps.core.seo import seo, seo_from_obj
from apps.livre.models import Livre
from apps.personnes.models import Personne
from apps.temoignages.models import Temoignage

from .models import Accueil, Page


def _get_livre():
    return Livre.objects.first()


def home(request):
    livre = _get_livre()
    temoignages = Temoignage.objects.filter(statut=Temoignage.STATUT_PUBLIE, mis_en_avant=True)[:6]
    actualites = Actualite.objects.filter(statut=Actualite.STATUT_PUBLIE)[:3]
    accueil = Accueil.get_solo()
    return render(
        request,
        "pages/home.html",
        {
            "livre": livre,
            "temoignages": temoignages,
            "actualites": actualites,
            "accueil": accueil,
            **seo_from_obj(request, accueil),
        },
    )


def page_livre(request):
    livre = _get_livre()
    return render(
        request,
        "pages/livre.html",
        {
            "livre": livre,
            **seo(
                request,
                title=f"Le livre · Bruno Boulais",
                description=(
                    "« Jacques Bertin, le géant discret de la chanson » — biographie"
                    " signée Bruno Boulais, aux Éditions du Petit Pavé."
                ),
            ),
        },
    )


def page_bertin(request):
    personne = Personne.objects.filter(role=Personne.ROLE_SUJET).first()
    return render(
        request,
        "pages/bertin.html",
        {
            "personne": personne,
            **seo(
                request,
                title="Jacques Bertin · Bruno Boulais",
                description=(
                    "Le chanteur-poète Jacques Bertin (né en 1946) : 20 albums et"
                    " une œuvre monumentale, racontés par Bruno Boulais."
                ),
            ),
        },
    )


def page_auteur(request):
    personne = Personne.objects.filter(role=Personne.ROLE_AUTEUR).first()
    return render(
        request,
        "pages/auteur.html",
        {
            "personne": personne,
            **seo(
                request,
                title="L'auteur · Bruno Boulais",
                description=(
                    "Bruno Boulais, auteur installé près de Dax, biographe de"
                    " Jacques Bertin. Présentation, engagements et parcours."
                ),
            ),
        },
    )


def mentions_legales(request):
    return render(
        request,
        "pages/mentions.html",
        seo(request, title="Mentions légales · Bruno Boulais"),
    )


def styleguide(request):
    if not settings.DEBUG:
        raise Http404
    return render(request, "pages/styleguide.html", {})


def page_detail(request, slug):
    page = get_object_or_404(Page, slug=slug, published=True)
    return render(
        request,
        "pages/page_detail.html",
        {"page": page, **seo_from_obj(request, page, title_fallback=page.title)},
    )
