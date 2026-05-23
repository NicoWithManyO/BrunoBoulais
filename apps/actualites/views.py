from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.core.seo import seo, seo_from_obj

from .models import Actualite


def liste(request):
    qs = Actualite.objects.filter(statut=Actualite.STATUT_PUBLIE)
    today = timezone.localdate()
    a_venir = qs.filter(date_evenement__gte=today).order_by("date_evenement")
    passees = qs.exclude(date_evenement__gte=today).order_by("-date_evenement", "-date_publication")
    return render(
        request,
        "actualites/liste.html",
        {
            "a_venir": a_venir,
            "passees": passees,
            **seo(
                request,
                title="Actualités & dédicaces · Bruno Boulais",
                description=(
                    "Toutes les dédicaces, rencontres et parutions liées au livre"
                    " de Bruno Boulais sur Jacques Bertin."
                ),
            ),
        },
    )


def detail(request, slug):
    obj = get_object_or_404(Actualite, slug=slug, statut=Actualite.STATUT_PUBLIE)
    fallback_image = obj.image_principale.image if obj.image_principale else None
    return render(
        request,
        "actualites/detail.html",
        {
            "obj": obj,
            **seo_from_obj(
                request,
                obj,
                title_fallback=f"{obj.titre} · Bruno Boulais",
                description_fallback=(obj.chapo or "")[:160] or None,
                og_type="article",
            ),
            # Fall back to the lead image as og:image when no explicit one is set.
            **(seo(request, og_image=fallback_image) if fallback_image and not obj.og_image else {}),
        },
    )
