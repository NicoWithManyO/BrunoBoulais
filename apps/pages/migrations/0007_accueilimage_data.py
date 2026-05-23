"""Copy Accueil.hero_image (singleton) into AccueilImage at position 0.

Runs between the schema creation of AccueilImage (0006) and the removal of
Accueil.hero_image (0008). Forward path preserves the file (same stored name);
reverse copies the first AccueilImage back into the old Accueil.hero_image
column so the migration is safely undoable.
"""
from django.db import migrations


def copy_hero_forward(apps, schema_editor):
    Accueil = apps.get_model("pages", "Accueil")
    AccueilImage = apps.get_model("pages", "AccueilImage")
    AccueilImage.objects.bulk_create([
        AccueilImage(accueil=a, image=a.hero_image.name, position=0)
        for a in Accueil.objects.exclude(hero_image="").exclude(hero_image__isnull=True)
    ])


def copy_hero_reverse(apps, schema_editor):
    Accueil = apps.get_model("pages", "Accueil")
    AccueilImage = apps.get_model("pages", "AccueilImage")
    for a in Accueil.objects.all():
        first = AccueilImage.objects.filter(accueil=a).order_by("position", "pk").first()
        if first:
            a.hero_image = first.image.name
            a.save(update_fields=["hero_image"])


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0006_images_create"),
    ]

    operations = [
        migrations.RunPython(copy_hero_forward, copy_hero_reverse),
    ]
