"""Aligne le `Site` (django.contrib.sites) avec settings.SITE_DOMAIN.

Sans cette migration, le sitemap.xml expose `https://example.com/...`
(la valeur par défaut posée par Django à l'install). Cette migration :

- crée le Site (id=SITE_ID) s'il n'existe pas,
- répare le default `example.com` au premier `migrate` après install,
- met à jour le domaine si l'env `SITE_DOMAIN` change.

Idempotente : ne fait rien quand la DB est déjà en cohérence avec settings.
"""
from django.conf import settings
from django.db import migrations


def _set_site(apps, schema_editor):
    Site = apps.get_model("sites", "Site")
    domain = getattr(settings, "SITE_DOMAIN", None)
    name = getattr(settings, "SITE_NAME", None) or "Bruno Boulais"
    if not domain:
        return
    site, created = Site.objects.get_or_create(
        id=settings.SITE_ID,
        defaults={"domain": domain, "name": name},
    )
    if created:
        return
    changed = []
    if site.domain != domain:
        site.domain = domain
        changed.append("domain")
    if site.name != name:
        site.name = name
        changed.append("name")
    if changed:
        site.save(update_fields=changed)


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("sites", "0002_alter_domain_unique"),
    ]

    operations = [
        migrations.RunPython(_set_site, _noop),
    ]
