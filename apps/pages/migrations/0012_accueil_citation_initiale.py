from django.core.cache import cache
from django.db import migrations

PULL_QUOTE_TEXTE = (
    "Ses chansons ne séduisent pas, elles touchent. "
    "Ses poèmes ne décorent pas, ils dévoilent. "
    "C'est peut-être pour cela qu'il a, depuis si longtemps, ce petit nombre "
    "de lecteurs et d'auditeurs qui ne le lâchent pas - comme on ne lâche pas "
    "un ami, comme on ne lâche pas une braise."
)
PULL_QUOTE_AUTEUR = "Bruno Boulais"


def set_citation(apps, schema_editor):
    """Injecte la citation historique de la home, sans écraser une saisie existante."""
    Accueil = apps.get_model("pages", "Accueil")
    obj, _ = Accueil.objects.get_or_create(pk=1)
    changed = False
    if not obj.pull_quote_texte:
        obj.pull_quote_texte = PULL_QUOTE_TEXTE
        changed = True
    if not obj.pull_quote_auteur:
        obj.pull_quote_auteur = PULL_QUOTE_AUTEUR
        changed = True
    if changed:
        obj.save()
        # Le save() du modèle historique n'invalide pas le cache du singleton ;
        # on le purge à la main (cf. CACHE_KEY_ACCUEIL dans apps/pages/models.py).
        cache.delete("pages_accueil")


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0011_accueil_pull_quote_commentaire"),
    ]

    operations = [
        migrations.RunPython(set_citation, migrations.RunPython.noop),
    ]
