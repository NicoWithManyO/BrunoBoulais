from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordChangeDoneView,
    PasswordChangeView,
)
from django.urls import path, reverse_lazy
from django.utils.decorators import method_decorator

from . import views
from .views import gestion_required

app_name = "gestion"


class _GestionPasswordChangeView(PasswordChangeView):
    template_name = "gestion/mot_de_passe.html"
    success_url = reverse_lazy("gestion:password_change_done")


class _GestionPasswordChangeDoneView(PasswordChangeDoneView):
    template_name = "gestion/mot_de_passe_ok.html"


_GestionPasswordChangeView.dispatch = method_decorator(gestion_required)(
    _GestionPasswordChangeView.dispatch
)
_GestionPasswordChangeDoneView.dispatch = method_decorator(gestion_required)(
    _GestionPasswordChangeDoneView.dispatch
)


urlpatterns = [
    path("connexion/", LoginView.as_view(template_name="gestion/login.html"), name="login"),
    path("deconnexion/", LogoutView.as_view(), name="logout"),
    path("mot-de-passe/", _GestionPasswordChangeView.as_view(), name="password_change"),
    path(
        "mot-de-passe/ok/",
        _GestionPasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
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
]
