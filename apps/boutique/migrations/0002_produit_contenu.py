from django.db import migrations, models


def volume_vers_contenu(apps, schema_editor):
    """Reporte l'ancien volume_integrale (1/2/3) dans le nouveau champ contenu."""
    Produit = apps.get_model("boutique", "Produit")
    for produit in Produit.objects.exclude(volume_integrale=None):
        produit.contenu = str(produit.volume_integrale)
        produit.save(update_fields=["contenu"])


def contenu_vers_volume(apps, schema_editor):
    """Reverse : "1"/"2"/"3" reviennent en volume_integrale, "integrale" est ignoré."""
    Produit = apps.get_model("boutique", "Produit")
    for produit in Produit.objects.exclude(contenu=""):
        if produit.contenu in {"1", "2", "3"}:
            produit.volume_integrale = int(produit.contenu)
            produit.save(update_fields=["volume_integrale"])


class Migration(migrations.Migration):

    dependencies = [
        ("boutique", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="produit",
            name="contenu",
            field=models.CharField(
                blank=True,
                choices=[
                    ("1", "Volume 1"),
                    ("2", "Volume 2"),
                    ("3", "Volume 3"),
                    ("integrale", "Intégrale (les 3 volumes)"),
                ],
                help_text="Si renseigné, une modale « voir le contenu » liste les CD/titres. "
                "« Intégrale » affiche les 3 volumes.",
                max_length=10,
                verbose_name="Contenu à afficher",
            ),
        ),
        migrations.RunPython(volume_vers_contenu, contenu_vers_volume),
        migrations.RemoveField(
            model_name="produit",
            name="volume_integrale",
        ),
    ]
