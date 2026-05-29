from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import pre_delete
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from apps.core.fields import RichTextField
from apps.core.models import (
    CarrouselSettingsMixin,
    OrderedImage,
    SeoMixin,
    TimestampedModel,
    delete_image_file,
)
from apps.core.uploads import (
    actualites_contenu_upload_to,
    actualites_image_upload_to,
    actualites_upload_to,
)
from apps.core.validators import IMAGE_VALIDATORS

CACHE_KEY_ACTUALITES_PAGE = "actualites_page"


class Actualite(TimestampedModel, SeoMixin, CarrouselSettingsMixin):
    """A dated piece of news (signing, event, press, etc.)."""

    TYPE_DEDICACE = "dedicace"
    TYPE_NEWS = "news"
    TYPE_PRESSE = "presse"
    TYPE_CHOICES = [
        (TYPE_DEDICACE, "Dédicace / rencontre"),
        (TYPE_NEWS, "Actualité"),
        (TYPE_PRESSE, "Presse"),
    ]

    STATUT_BROUILLON = "brouillon"
    STATUT_PUBLIE = "publie"
    STATUT_CHOICES = [
        (STATUT_BROUILLON, "Brouillon"),
        (STATUT_PUBLIE, "Publiée"),
    ]

    titre = models.CharField("Titre", max_length=200)
    slug = models.SlugField("Identifiant URL", max_length=220, unique=True, blank=True)
    type = models.CharField("Type", max_length=20, choices=TYPE_CHOICES, default=TYPE_NEWS)
    statut = models.CharField("Statut", max_length=20, choices=STATUT_CHOICES, default=STATUT_BROUILLON)

    date_evenement = models.DateField(
        "Date de l'événement", null=True, blank=True,
        help_text="Pour les dédicaces et événements."
    )
    heure_debut = models.TimeField("Heure début", null=True, blank=True)
    heure_fin = models.TimeField("Heure fin", null=True, blank=True)
    lieu = models.CharField("Lieu", max_length=200, blank=True)
    ville = models.CharField("Ville", max_length=100, blank=True)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    chapo = models.CharField(
        "Chapeau", max_length=300, blank=True,
        help_text="Phrase d'accroche affichée dans les listes."
    )
    contenu = RichTextField("Contenu", blank=True)

    date_publication = models.DateTimeField("Date de publication", default=timezone.now)

    class Meta:
        ordering = ["-date_evenement", "-date_publication"]
        verbose_name = "Actualité"
        verbose_name_plural = "Actualités"

    def __str__(self):
        return self.titre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.titre)[:220]
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("actualites:detail", args=[self.slug])

    @property
    def est_a_venir(self):
        if not self.date_evenement:
            return False
        return self.date_evenement >= timezone.localdate()

    @property
    def image_principale(self):
        """First image, used as the OG/share image and as a fallback in lists."""
        return self.images.first()


class ActualiteImage(OrderedImage):
    """An image attached to an Actualite (1-N for carousel)."""

    actualite = models.ForeignKey(
        Actualite, related_name="images", on_delete=models.CASCADE,
        verbose_name="Actualité",
    )
    image = models.ImageField(
        "Image", upload_to=actualites_image_upload_to, validators=IMAGE_VALIDATORS,
    )


pre_delete.connect(delete_image_file, sender=ActualiteImage)


class ActualiteImageContenu(OrderedImage):
    """Images insérables dans le corps du texte via le repère `[image:N]`.

    Lot séparé du carrousel : ces images n'apparaissent que là où l'éditeur
    place leur repère dans le contenu.
    """

    actualite = models.ForeignKey(
        Actualite, related_name="images_contenu", on_delete=models.CASCADE,
        verbose_name="Actualité",
    )
    image = models.ImageField(
        "Image", upload_to=actualites_contenu_upload_to, validators=IMAGE_VALIDATORS,
    )


pre_delete.connect(delete_image_file, sender=ActualiteImageContenu)


class ActualitesPage(TimestampedModel):
    """Singleton holding the editable header of the public /actualites/ page."""

    eyebrow = models.CharField("Surtitre", max_length=80, blank=True)
    titre = models.CharField("Titre", max_length=120, blank=True)
    intro = RichTextField("Texte d'introduction", blank=True)

    class Meta:
        verbose_name = "En-tête /actualités/"
        verbose_name_plural = "En-tête /actualités/"

    def __str__(self):
        return "En-tête /actualités/"

    def clean(self):
        if not self.pk and ActualitesPage.objects.exists():
            raise ValidationError("Un seul en-tête peut exister (singleton).")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY_ACTUALITES_PAGE)

    @classmethod
    def get_solo(cls):
        obj = cache.get(CACHE_KEY_ACTUALITES_PAGE)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(CACHE_KEY_ACTUALITES_PAGE, obj, 300)
        return obj
