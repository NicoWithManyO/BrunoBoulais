from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0012_accueil_citation_initiale"),
    ]

    operations = [
        migrations.RenameField("accueil", "pull_quote_texte", "citation_texte"),
        migrations.RenameField("accueil", "pull_quote_auteur", "citation_auteur"),
        migrations.RenameField(
            "accueil", "pull_quote_commentaire", "citation_commentaire"
        ),
    ]
