from django.db import models


class TimestampedModel(models.Model):
    """Base abstract model with created/updated timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")

    class Meta:
        abstract = True


class SeoMixin(models.Model):
    """Mixin for SEO metadata."""

    seo_title = models.CharField(
        "Titre SEO", max_length=70, blank=True,
        help_text="Titre affiché par Google (~60 caractères). Laisser vide pour titre auto."
    )
    seo_description = models.CharField(
        "Description SEO", max_length=160, blank=True,
        help_text="Description affichée par Google (~150 caractères)."
    )
    og_image = models.ImageField(
        "Image de partage", upload_to="og/", blank=True, null=True,
        help_text="Image affichée lors d'un partage sur les réseaux sociaux."
    )

    class Meta:
        abstract = True
