from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from taggit.managers import TaggableManager

from apps.core.fields import RichTextField
from apps.core.models import TimestampedModel
from apps.core.uploads import galerie_upload_to
from apps.core.validators import MEDIA_VALIDATORS

CACHE_KEY_GALERIE_PAGE = "galerie_page"


class Media(TimestampedModel):
    """Image or video file."""

    TYPE_IMAGE = "image"
    TYPE_VIDEO = "video"
    TYPE_CHOICES = [(TYPE_IMAGE, "Image"), (TYPE_VIDEO, "Vidéo")]

    CATEGORIE_BERTIN = "bertin"
    CATEGORIE_LIVRE = "livre"
    CATEGORIE_DEDICACE = "dedicace"
    CATEGORIE_AUTEUR = "auteur"
    CATEGORIE_AUTRE = "autre"
    CATEGORIE_CHOICES = [
        (CATEGORIE_BERTIN, "Jacques Bertin"),
        (CATEGORIE_LIVRE, "Le livre"),
        (CATEGORIE_DEDICACE, "Dédicaces"),
        (CATEGORIE_AUTEUR, "Bruno Boulais"),
        (CATEGORIE_AUTRE, "Autre"),
    ]

    type = models.CharField("Type", max_length=10, choices=TYPE_CHOICES, default=TYPE_IMAGE)
    categorie = models.CharField(
        "Catégorie", max_length=20, choices=CATEGORIE_CHOICES, default=CATEGORIE_AUTRE
    )
    fichier = models.FileField("Fichier", upload_to=galerie_upload_to, validators=MEDIA_VALIDATORS)
    legende = models.CharField("Légende", max_length=300, blank=True)
    alt = models.CharField(
        "Texte alternatif", max_length=200, blank=True,
        help_text="Décrit l'image pour les lecteurs d'écran."
    )
    position = models.PositiveIntegerField("Position", default=0)
    publie = models.BooleanField("Publié", default=True)

    tags = TaggableManager(blank=True)

    class Meta:
        ordering = ["position", "-created_at"]
        verbose_name = "Média"
        verbose_name_plural = "Médias"

    def __str__(self):
        return self.legende or self.fichier.name


class GaleriePage(TimestampedModel):
    """Singleton holding the editable header of the public /galerie/ page."""

    eyebrow = models.CharField("Surtitre", max_length=80, blank=True)
    titre = models.CharField("Titre", max_length=120, blank=True)
    intro = RichTextField("Texte d'introduction", blank=True)

    class Meta:
        verbose_name = "En-tête /galerie/"
        verbose_name_plural = "En-tête /galerie/"

    def __str__(self):
        return "En-tête /galerie/"

    def clean(self):
        if not self.pk and GaleriePage.objects.exists():
            raise ValidationError("Un seul en-tête peut exister (singleton).")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY_GALERIE_PAGE)

    @classmethod
    def get_solo(cls):
        obj = cache.get(CACHE_KEY_GALERIE_PAGE)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(CACHE_KEY_GALERIE_PAGE, obj, 300)
        return obj
