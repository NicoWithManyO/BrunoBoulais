from django.contrib import admin

from .models import Chanson


@admin.register(Chanson)
class ChansonAdmin(admin.ModelAdmin):
    list_display = ("titre", "album", "annee", "position", "publie")
    list_filter = ("publie",)
    search_fields = ("titre", "album", "url_youtube")
    list_editable = ("position", "publie")
    ordering = ("position", "-created_at")
