from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import Actualite


def liste(request):
    qs = Actualite.objects.filter(statut=Actualite.STATUT_PUBLIE)
    today = timezone.localdate()
    a_venir = qs.filter(date_evenement__gte=today).order_by("date_evenement")
    passees = qs.exclude(date_evenement__gte=today).order_by("-date_evenement", "-date_publication")
    return render(request, "actualites/liste.html", {"a_venir": a_venir, "passees": passees})


def detail(request, slug):
    obj = get_object_or_404(Actualite, slug=slug, statut=Actualite.STATUT_PUBLIE)
    return render(request, "actualites/detail.html", {"obj": obj})
