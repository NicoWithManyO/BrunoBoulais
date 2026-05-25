from django.contrib import admin

from .models import Billet


@admin.register(Billet)
class BilletAdmin(admin.ModelAdmin):
    list_display = ("titre", "statut", "date_publication")
    list_filter = ("statut",)
    search_fields = ("titre", "contenu")
    prepopulated_fields = {"slug": ("titre",)}
    date_hierarchy = "date_publication"
