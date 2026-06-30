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
]
