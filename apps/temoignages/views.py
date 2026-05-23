from django.shortcuts import render

from .models import Temoignage


def liste(request):
    qs = Temoignage.objects.filter(statut=Temoignage.STATUT_PUBLIE)
    return render(request, "temoignages/liste.html", {"temoignages": qs})
