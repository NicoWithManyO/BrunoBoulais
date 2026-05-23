from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import SeoMixin, TimestampedModel


class Actualite(TimestampedModel, SeoMixin):
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
    contenu = models.TextField("Contenu", blank=True, help_text="HTML autorisé.")
    image = models.ImageField("Image", upload_to="actualites/", blank=True, null=True)

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
