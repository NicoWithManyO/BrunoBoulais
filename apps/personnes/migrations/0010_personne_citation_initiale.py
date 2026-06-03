from django.db import migrations

CITATIONS = {
    "sujet": {
        "texte": (
            "Dans un monde saturé de bruit, Jacques Bertin est une source claire : "
            "celui qui ne crie pas pour qu’on l’entende, mais qui se penche pour qu’on l’écoute."
        ),
        "auteur": "d’après Jean-Claude Guillebaud",
    },
    "auteur": {
        "texte": (
            "Écrire sur Bertin, c’est d’abord apprendre à se taire un instant, "
            "pour mieux l’écouter."
        ),
        "auteur": "Bruno Boulais",
    },
}


def set_citations(apps, schema_editor):
    """Injecte les citations historiques des pages Personne, sans écraser une saisie existante."""
    Personne = apps.get_model("personnes", "Personne")
    for role, data in CITATIONS.items():
        obj = Personne.objects.filter(role=role).first()
        if obj is None:
            continue
        changed = False
        if not obj.citation_texte:
            obj.citation_texte = data["texte"]
            changed = True
        if not obj.citation_auteur:
            obj.citation_auteur = data["auteur"]
            changed = True
        if changed:
            obj.save()


class Migration(migrations.Migration):

    dependencies = [
        ("personnes", "0009_personne_citation_auteur_and_more"),
    ]

    operations = [
        migrations.RunPython(set_citations, migrations.RunPython.noop),
    ]
