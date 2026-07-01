from django.urls import path

from . import views

app_name = "boutique"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("chapeau/", views.chapeau_voir, name="chapeau"),
    path("chapeau/ajouter/<int:pk>/", views.chapeau_ajouter, name="chapeau_ajouter"),
    path("chapeau/modifier/<int:pk>/", views.chapeau_modifier, name="chapeau_modifier"),
    path("chapeau/retirer/<int:pk>/", views.chapeau_retirer, name="chapeau_retirer"),
    path("chapeau/vider/", views.chapeau_vider, name="chapeau_vider"),
    path("commande/", views.commande, name="commande"),
    path("merci/", views.merci, name="merci"),
    path("paiement/cb/<int:pk>/", views.paiement_cb, name="paiement_cb"),
    path("paiement/success/", views.paiement_success, name="paiement_success"),
    path("paiement/annule/", views.paiement_annule, name="paiement_annule"),
    path("webhook/stripe/", views.webhook_stripe, name="webhook_stripe"),
]
