"""Copy Livre.couverture (singleton) into LivreImage at position 0.

Runs between the schema creation of LivreImage (0004) and the removal of
Livre.couverture (0006). Forward path preserves the file (same stored name);
reverse copies the first LivreImage back into the old Livre.couverture
column so the migration is safely undoable.
"""
from django.db import migrations


def copy_couverture_forward(apps, schema_editor):
    Livre = apps.get_model("livre", "Livre")
    LivreImage = apps.get_model("livre", "LivreImage")
    LivreImage.objects.bulk_create([
        LivreImage(livre=l, image=l.couverture.name, position=0)
        for l in Livre.objects.exclude(couverture="").exclude(couverture__isnull=True)
    ])


def copy_couverture_reverse(apps, schema_editor):
    Livre = apps.get_model("livre", "Livre")
    LivreImage = apps.get_model("livre", "LivreImage")
    for l in Livre.objects.all():
        first = LivreImage.objects.filter(livre=l).order_by("position", "pk").first()
        if first:
            l.couverture = first.image.name
            l.save(update_fields=["couverture"])


class Migration(migrations.Migration):

    dependencies = [
        ("livre", "0004_images_create"),
    ]

    operations = [
        migrations.RunPython(copy_couverture_forward, copy_couverture_reverse),
    ]
