from django.urls import path

from . import views

app_name = "pages"

urlpatterns = [
    path("", views.home, name="home"),
    path("le-livre/", views.page_livre, name="livre"),
    path("jacques-bertin/", views.page_bertin, name="bertin"),
    path("l-auteur/", views.page_auteur, name="auteur"),
    path("mentions-legales/", views.mentions_legales, name="mentions"),
    path("styleguide/", views.styleguide, name="styleguide"),
    path("<slug:slug>/", views.page_detail, name="page"),
]
