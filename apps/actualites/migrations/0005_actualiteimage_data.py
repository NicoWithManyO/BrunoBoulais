"""Copy each Actualite.image (single ImageField) into ActualiteImage at position 0.

Runs between the schema creation of ActualiteImage (0004) and the removal of
Actualite.image (0006). The forward path preserves all existing files; the
reverse copies the first ActualiteImage back into the old Actualite.image
column so the migration is safely undoable.
"""
from django.db import migrations


def copy_images_forward(apps, schema_editor):
    Actualite = apps.get_model("actualites", "Actualite")
    ActualiteImage = apps.get_model("actualites", "ActualiteImage")
    # Reuse the same stored path, no file copy.
    ActualiteImage.objects.bulk_create([
        ActualiteImage(actualite=actu, image=actu.image.name, position=0)
        for actu in Actualite.objects.exclude(image="").exclude(image__isnull=True)
    ])


def copy_images_reverse(apps, schema_editor):
    Actualite = apps.get_model("actualites", "Actualite")
    ActualiteImage = apps.get_model("actualites", "ActualiteImage")
    for actu in Actualite.objects.all():
        first = ActualiteImage.objects.filter(actualite=actu).order_by("position", "pk").first()
        if first:
            actu.image = first.image.name
            actu.save(update_fields=["image"])


class Migration(migrations.Migration):

    dependencies = [
        ("actualites", "0004_actualiteimage_create"),
    ]

    operations = [
        migrations.RunPython(copy_images_forward, copy_images_reverse),
    ]
