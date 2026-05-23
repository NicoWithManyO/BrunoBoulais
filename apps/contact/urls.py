from django.urls import path

from . import views

app_name = "contact"

urlpatterns = [
    path("", views.contact, name="form"),
    path("merci/", views.merci, name="merci"),
]
