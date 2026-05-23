from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views

app_name = "gestion"

urlpatterns = [
    path("connexion/", LoginView.as_view(template_name="gestion/login.html"), name="login"),
    path("deconnexion/", LogoutView.as_view(), name="logout"),
    path("", views.dashboard, name="dashboard"),
    # Actualités
    path("actualites/", views.actualites_liste, name="actualites_liste"),
    path("actualites/ajouter/", views.actualite_form, name="actualite_ajouter"),
    path("actualites/<int:pk>/", views.actualite_form, name="actualite_modifier"),
    path("actualites/<int:pk>/supprimer/", views.actualite_supprimer, name="actualite_supprimer"),
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
    # Pages
    path("pages/", views.pages_liste, name="pages_liste"),
    path("pages/<slug:slug>/", views.page_editer, name="page_editer"),
    # Livre
    path("livre/", views.livre_form, name="livre"),
    # Paramètres
    path("parametres/", views.parametres_form, name="parametres"),
]
