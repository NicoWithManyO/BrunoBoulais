"""Stub views — réelles implémentations dans l'étape Interface de gestion."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse


def _placeholder(request, *args, **kwargs):
    return HttpResponse("À venir.")


dashboard = login_required(_placeholder)
actualites_liste = login_required(_placeholder)
actualite_form = login_required(_placeholder)
actualite_supprimer = login_required(_placeholder)
temoignages_liste = login_required(_placeholder)
temoignage_form = login_required(_placeholder)
temoignage_supprimer = login_required(_placeholder)
galerie_liste = login_required(_placeholder)
media_form = login_required(_placeholder)
media_supprimer = login_required(_placeholder)
messages_liste = login_required(_placeholder)
message_detail = login_required(_placeholder)
pages_liste = login_required(_placeholder)
page_editer = login_required(_placeholder)
livre_form = login_required(_placeholder)
parametres_form = login_required(_placeholder)
