from django.db import models

from apps.core.fields import RichTextField
from apps.core.models import TimestampedModel


class Temoignage(TimestampedModel):
    """Reader testimonial."""

    STATUT_BROUILLON = "brouillon"
    STATUT_PUBLIE = "publie"
    STATUT_REFUSE = "refuse"
    STATUT_CHOICES = [
        (STATUT_BROUILLON, "Brouillon"),
        (STATUT_PUBLIE, "Publié"),
        (STATUT_REFUSE, "Refusé"),
    ]

    auteur = models.CharField("Auteur", max_length=120)
    source = models.CharField(
        "Source", max_length=200, blank=True,
        help_text="Optionnel : ville, lien, contexte (ex. 'Mairie de Pouillon, Facebook')."
    )
    texte = RichTextField("Texte")
    statut = models.CharField("Statut", max_length=20, choices=STATUT_CHOICES, default=STATUT_BROUILLON)
    mis_en_avant = models.BooleanField(
        "Mis en avant", default=False,
        help_text="Affiché dans le carrousel de la page d'accueil."
    )
    position = models.PositiveIntegerField("Position", default=0)

    class Meta:
        ordering = ["position", "-created_at"]
        verbose_name = "Témoignage"
        verbose_name_plural = "Témoignages"

    def __str__(self):
        return f"{self.auteur} — {self.texte[:60]}…"
