from django.urls import path

from . import views

app_name = "contact"

urlpatterns = [
    path("", views.contact, name="form"),
    path("merci/", views.merci, name="merci"),
    # Nouvelle page de commande (page de travail, swap vers "" à venir).
    path("v2/", views.commande, name="commande"),
    path("v2/merci/", views.commande_merci, name="commande_merci"),
    path("paiement/", views.paiement_checkout, name="paiement"),
    path("paiement/webhook/", views.paiement_webhook, name="paiement_webhook"),
]
