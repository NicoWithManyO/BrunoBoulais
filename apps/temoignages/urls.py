from django.urls import path

from . import views

app_name = "temoignages"

urlpatterns = [
    path("", views.liste, name="liste"),
]
