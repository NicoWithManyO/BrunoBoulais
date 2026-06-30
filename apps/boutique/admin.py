from django.contrib import admin

from .models import Commande, LigneCommande, Produit


@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = ("nom", "reference", "prix_cents", "position", "publie")
    list_filter = ("publie", "dedicacable")
    search_fields = ("nom", "reference")
    list_editable = ("position", "publie")
    prepopulated_fields = {"slug": ("nom",)}
    ordering = ("position", "-created_at")


class LigneCommandeInline(admin.TabularInline):
    model = LigneCommande
    extra = 0


@admin.register(Commande)
class CommandeAdmin(admin.ModelAdmin):
    list_display = ("reference_commande", "nom", "mode_paiement", "statut", "montant_total_cents", "created_at")
    list_filter = ("statut", "mode_paiement", "lu", "archive")
    search_fields = ("reference_commande", "nom", "email")
    inlines = [LigneCommandeInline]
