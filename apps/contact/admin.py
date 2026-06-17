from django.contrib import admin

from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "nom", "sujet", "mode_paiement", "nb_exemplaires", "paye", "notified", "lu", "created_at"
    )
    list_editable = ("paye",)  # Bruno coche « Payé » à la main pour chèque/virement.
    list_filter = ("paye", "notified", "sujet", "mode_paiement", "lu", "archive")
    search_fields = ("nom", "email", "contenu")
    readonly_fields = ("created_at", "updated_at", "stripe_session_id")
