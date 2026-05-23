from django.db import models

from apps.core.uploads import og_upload_to
from apps.core.validators import IMAGE_VALIDATORS


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
        "Image de partage", upload_to=og_upload_to, blank=True, null=True,
        validators=IMAGE_VALIDATORS,
        help_text="Image affichée lors d'un partage sur les réseaux sociaux."
    )

    class Meta:
        abstract = True


class OrderedImage(models.Model):
    """Abstract base for 1-N "gallery / carousel" image attached to a parent.

    Concrete subclasses must declare:
      - a `parent` ForeignKey with `related_name='images'`
      - an `image = ImageField(upload_to=..., validators=IMAGE_VALIDATORS)`

    Pair with `delete_image_file` via `pre_delete.connect(..., sender=Cls)` in
    the subclass module to clean up files on cascade delete (handled per-class
    because Django bulk deletes bypass Model.delete()).
    """

    position = models.PositiveSmallIntegerField(
        "Ordre", default=0,
        help_text="Plus le nombre est petit, plus l'image apparaît tôt."
    )
    alt = models.CharField(
        "Texte alternatif", max_length=180, blank=True,
        help_text="Décrit l'image pour les lecteurs d'écran. Laisser vide reprend le titre du parent."
    )

    class Meta:
        abstract = True
        ordering = ["position", "pk"]

    def __str__(self):
        return f"Image #{self.pk} (pos {self.position})"


def delete_image_file(sender, instance, **kwargs):
    """pre_delete handler that removes the underlying file from storage."""
    if getattr(instance, "image", None):
        instance.image.delete(save=False)
