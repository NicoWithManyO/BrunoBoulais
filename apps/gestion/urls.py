from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordChangeDoneView,
    PasswordChangeView,
)
from django.urls import path, reverse_lazy

from . import views
from .views import gestion_required

app_name = "gestion"

_password_change = gestion_required(PasswordChangeView.as_view(
    template_name="gestion/mot_de_passe.html",
    success_url=reverse_lazy("gestion:password_change_done"),
))
_password_change_done = gestion_required(PasswordChangeDoneView.as_view(
    template_name="gestion/mot_de_passe_ok.html",
))

urlpatterns = [
    path("connexion/", LoginView.as_view(template_name="gestion/login.html"), name="login"),
    path("deconnexion/", LogoutView.as_view(), name="logout"),
    path("mot-de-passe/", _password_change, name="password_change"),
    path("mot-de-passe/ok/", _password_change_done, name="password_change_done"),
    path("", views.dashboard, name="dashboard"),
    # Actualités
    path("actualites/", views.actualites_liste, name="actualites_liste"),
    path("actualites/ajouter/", views.actualite_form, name="actualite_ajouter"),
    path("actualites/<int:pk>/", views.actualite_form, name="actualite_modifier"),
    path("actualites/<int:pk>/supprimer/", views.actualite_supprimer, name="actualite_supprimer"),
    # Carnet (billets courts)
    path("carnet/", views.billets_liste, name="billets_liste"),
    path("carnet/ajouter/", views.billet_form, name="billet_ajouter"),
    path("carnet/<int:pk>/", views.billet_form, name="billet_modifier"),
    path("carnet/<int:pk>/supprimer/", views.billet_supprimer, name="billet_supprimer"),
    # Discothèque (chansons)
    path("discotheque/", views.chansons_liste, name="chansons_liste"),
    path("discotheque/ajouter/", views.chanson_form, name="chanson_ajouter"),
    path("discotheque/<int:pk>/", views.chanson_form, name="chanson_modifier"),
    path("discotheque/<int:pk>/supprimer/", views.chanson_supprimer, name="chanson_supprimer"),
    # Boutique (produits)
    path("boutique/", views.produits_liste, name="produits_liste"),
    path("boutique/ajouter/", views.produit_form, name="produit_ajouter"),
    path("boutique/<int:pk>/", views.produit_form, name="produit_modifier"),
    path("boutique/<int:pk>/supprimer/", views.produit_supprimer, name="produit_supprimer"),
    # Frais de port (tranches de poids)
    path("frais-port/", views.tranches_port_liste, name="tranches_port_liste"),
    path("frais-port/ajouter/", views.tranche_port_form, name="tranche_port_ajouter"),
    path("frais-port/<int:pk>/", views.tranche_port_form, name="tranche_port_modifier"),
    path("frais-port/<int:pk>/supprimer/", views.tranche_port_supprimer, name="tranche_port_supprimer"),
    # Témoignages
    path("temoignages/", views.temoignages_liste, name="temoignages_liste"),
    path("temoignages/ajouter/", views.temoignage_form, name="temoignage_ajouter"),
    path("temoignages/<int:pk>/", views.temoignage_form, name="temoignage_modifier"),
    path("temoignages/<int:pk>/supprimer/", views.temoignage_supprimer, name="temoignage_supprimer"),
    # Galerie
    path("galerie/", views.galerie_liste, name="galerie_liste"),
    path("galerie/ajouter/", views.media_form, name="media_ajouter"),
    path("galerie/<int:pk>/", views.media_form, name="media_modifier"),
    path("galerie/<int:pk>/supprimer/", views.media_supprimer, name="media_supprimer"),
    # Messages
    path("messages/", views.messages_liste, name="messages_liste"),
    path("messages/<int:pk>/", views.message_detail, name="message_detail"),
    # Commandes (boutique)
    path("commandes/", views.commandes_liste, name="commandes_liste"),
    path("commandes/<int:pk>/", views.commande_detail, name="commande_detail"),
    # Page /contact/ (singleton — en-tête éditable)
    path("contact/", views.contact_page_form, name="contact_page"),
    # Page d'accueil (singleton)
    path("accueil/", views.accueil_form, name="accueil"),
    # Personnes (Jacques Bertin & Bruno Boulais)
    path(
        "jacques-bertin/", views.personne_form,
        {"role": "sujet"}, name="personne_bertin",
    ),
    path(
        "l-auteur/", views.personne_form,
        {"role": "auteur"}, name="personne_auteur",
    ),
    # Livre
    path("livre/", views.livre_form, name="livre"),
    # Paramètres
    path("parametres/", views.parametres_form, name="parametres"),
    # HTMX endpoints: per-row image delete -----------------------------------
    path("accueil/images/<int:image_pk>/supprimer/", views.accueil_image_supprimer, name="accueil_image_supprimer"),
    path("livre/images/<int:image_pk>/supprimer/", views.livre_image_supprimer, name="livre_image_supprimer"),
    path("personnes/images/<int:image_pk>/supprimer/", views.personne_image_supprimer, name="personne_image_supprimer"),
    path("actualites/images/<int:image_pk>/supprimer/", views.actualite_image_supprimer, name="actualite_image_supprimer"),
    path("carnet/images-contenu/<int:image_pk>/supprimer/", views.billet_image_contenu_supprimer, name="billet_image_contenu_supprimer"),
    path("carnet/images-contenu/ajouter/", views.billet_image_contenu_ajouter, name="billet_image_contenu_ajouter_new"),
    path("carnet/<int:pk>/images-contenu/ajouter/", views.billet_image_contenu_ajouter, name="billet_image_contenu_ajouter"),
    path("carnet/<int:pk>/annuler/", views.billet_annuler, name="billet_annuler"),
    path("carnet/preview/", views.billet_preview, name="billet_preview_new"),
    path("carnet/<int:pk>/preview/", views.billet_preview, name="billet_preview"),
]
