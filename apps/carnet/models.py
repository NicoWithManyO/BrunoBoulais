from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.core.fields import RichTextField
from apps.core.models import TimestampedModel


class Billet(TimestampedModel):
    """Billet court (carnet de news) publié au fil des jours sur la home."""

    STATUT_BROUILLON = "brouillon"
    STATUT_PUBLIE = "publie"
    STATUT_CHOICES = [
        (STATUT_BROUILLON, "Brouillon"),
        (STATUT_PUBLIE, "Publié"),
    ]

    titre = models.CharField("Titre", max_length=200)
    slug = models.SlugField("Identifiant URL", max_length=220, unique=True, blank=True)
    contenu = RichTextField("Contenu")
    statut = models.CharField(
        "Statut", max_length=20, choices=STATUT_CHOICES, default=STATUT_BROUILLON,
    )
    date_publication = models.DateTimeField("Date de publication", default=timezone.now)

    class Meta:
        ordering = ["-date_publication"]
        verbose_name = "Billet"
        verbose_name_plural = "Billets"

    def __str__(self):
        return self.titre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.titre)[:220]
        super().save(*args, **kwargs)
