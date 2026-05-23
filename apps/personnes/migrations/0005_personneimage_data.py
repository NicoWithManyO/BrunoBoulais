"""Copy each Personne.portrait into PersonneImage at position 0.

Runs between the schema creation of PersonneImage (0004) and the removal of
Personne.portrait (0006). Forward path preserves files (same stored name);
reverse copies the first PersonneImage back into the old Personne.portrait
column so the migration is safely undoable.
"""
from django.db import migrations


def copy_portraits_forward(apps, schema_editor):
    Personne = apps.get_model("personnes", "Personne")
    PersonneImage = apps.get_model("personnes", "PersonneImage")
    PersonneImage.objects.bulk_create([
        PersonneImage(personne=p, image=p.portrait.name, position=0)
        for p in Personne.objects.exclude(portrait="").exclude(portrait__isnull=True)
    ])


def copy_portraits_reverse(apps, schema_editor):
    Personne = apps.get_model("personnes", "Personne")
    PersonneImage = apps.get_model("personnes", "PersonneImage")
    for p in Personne.objects.all():
        first = PersonneImage.objects.filter(personne=p).order_by("position", "pk").first()
        if first:
            p.portrait = first.image.name
            p.save(update_fields=["portrait"])


class Migration(migrations.Migration):

    dependencies = [
        ("personnes", "0004_images_create"),
    ]

    operations = [
        migrations.RunPython(copy_portraits_forward, copy_portraits_reverse),
    ]
