from django.contrib import admin

from .models import Chanson


@admin.register(Chanson)
class ChansonAdmin(admin.ModelAdmin):
    list_display = ("titre", "type", "album", "annee", "position", "publie")
    list_filter = ("type", "publie")
    search_fields = ("titre", "album", "url_youtube")
    list_editable = ("position", "publie")
    ordering = ("position", "-created_at")
