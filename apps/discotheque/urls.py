from django.urls import path

from . import views

app_name = "discotheque"

urlpatterns = [
    path("", views.liste, name="liste"),
]
