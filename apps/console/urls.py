from django.urls import path

from . import views

app_name = "console"

urlpatterns = [
    path("", views.console, name="console"),
    path("io/", views.api_io, name="io"),
    path("close/", views.api_close, name="close"),
    path("lock/", views.api_lock, name="lock"),
]
