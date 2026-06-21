from django.urls import path

from . import views

app_name = "contact"

urlpatterns = [
    path("", views.commande, name="form"),
    path("merci/", views.commande_merci, name="merci"),
]
