"""Crée en base le catalogue de la boutique (livre, volumes, intégrale, pack).

Idempotent : rejouable sans doublon (clé = slug). Réaligne les champs canoniques
(nom, prix, contenu, dédicace, poids) sur cette source de vérité, mais laisse
intactes l'illustration (ajoutée par Bruno), la position et la publication.
"""
from django.core.management.base import BaseCommand

from apps.boutique.models import CONTENU_INTEGRALE, Produit

# Catalogue de référence. Prix en centimes ; poids réels en grammes fournis par
# Bruno (intégrale 434 g, livre 360 g, volume 145 g ; pack = intégrale + livre).
# Dédicace réservée aux offres incluant le livre. (slug, defaults)
CATALOGUE = [
    ("livre", {
        "nom": "Livre", "prix_cents": 2000, "contenu": "",
        "dedicacable": True, "poids_g": 360,
    }),
    ("volume-1", {
        "nom": "Volume 1", "prix_cents": 2000, "contenu": "1",
        "dedicacable": False, "poids_g": 145,
    }),
    ("volume-2", {
        "nom": "Volume 2", "prix_cents": 2000, "contenu": "2",
        "dedicacable": False, "poids_g": 145,
    }),
    ("volume-3", {
        "nom": "Volume 3", "prix_cents": 2000, "contenu": "3",
        "dedicacable": False, "poids_g": 145,
    }),
    ("integrale", {
        "nom": "Intégrale (3 volumes — 15 CD)", "prix_cents": 6000,
        "contenu": CONTENU_INTEGRALE, "dedicacable": False, "poids_g": 434,
    }),
    ("pack-integrale-livre", {
        "nom": "Pack Intégrale + Livre", "prix_cents": 7500,
        "contenu": CONTENU_INTEGRALE, "dedicacable": True, "poids_g": 794,
    }),
]


class Command(BaseCommand):
    help = "Crée (ou réaligne) les produits de la boutique."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seed de la boutique…"))
        for slug, defaults in CATALOGUE:
            _, created = Produit.objects.update_or_create(slug=slug, defaults=defaults)
            verbe = "créé" if created else "mis à jour"
            self.stdout.write(f"  {defaults['nom']} — {verbe}.")
        self.stdout.write(self.style.SUCCESS("Terminé."))
