from django.contrib import admin

from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "nom", "sujet", "produit", "mode_paiement", "nb_exemplaires", "volumes",
        "mode_livraison", "point_relais_libelle", "dedicace", "paye", "notified", "lu", "created_at"
    )
    list_editable = ("paye",)  # Bruno coche « Payé » à la main pour chèque/virement.
    list_filter = ("paye", "notified", "sujet", "produit", "mode_paiement", "mode_livraison", "lu", "archive")
    search_fields = ("nom", "email", "contenu")
    readonly_fields = ("created_at", "updated_at", "point_relais_id")
