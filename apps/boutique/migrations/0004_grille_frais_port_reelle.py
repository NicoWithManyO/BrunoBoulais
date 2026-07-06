# Generated manually on 2026-07-06.

from django.db import migrations

# Grille Mondial Relay réelle (tarifs TTC au 15 juin 2026, envois France).
# Remplace la grille de départ approximative seedée en 0003. Reste éditable en
# gestion. (poids_max_g, prix_relais_cents, prix_domicile_cents)
GRILLE = [
    (250, 415, 499),
    (500, 415, 749),
    (1000, 599, 949),
    (2000, 799, 1099),
    (3000, 799, 1639),
    (4000, 999, 1639),
    (5000, 1599, 1639),
    (7000, 1599, 2499),
    (10000, 1599, 2499),
    (15000, 2599, 3149),
    (25000, 2599, 4299),
]


def set_grille(apps, schema_editor):
    TranchePort = apps.get_model("boutique", "TranchePort")
    TranchePort.objects.all().delete()
    TranchePort.objects.bulk_create(
        TranchePort(poids_max_g=p, prix_relais_cents=r, prix_domicile_cents=d)
        for p, r, d in GRILLE
    )


class Migration(migrations.Migration):

    dependencies = [
        ('boutique', '0003_trancheport_produit_poids_g'),
    ]

    operations = [
        # Remplacement complet ; l'ancienne grille de 0003 n'a pas de valeur à restaurer.
        migrations.RunPython(set_grille, migrations.RunPython.noop),
    ]
