from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.fields import RichTextField
from apps.core.models import TimestampedModel

CACHE_KEY_TEMOIGNAGES_PAGE = "temoignages_page"


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
    # mode="inline" matches how the value is rendered: as a single quoted
    # snippet inside <blockquote> on /temoignages/ and home.html (« … »).
    # Allows <strong>/<em>/<br> only; no <p> or lists. Keeps the editor
    # honest about the shape of the data.
    texte = RichTextField("Texte", mode="inline")
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


class TemoignagesPage(TimestampedModel):
    """Singleton holding the editable header of the public /temoignages/ page."""

    eyebrow = models.CharField("Surtitre", max_length=80, blank=True)
    titre = models.CharField("Titre", max_length=120, blank=True)
    intro = RichTextField("Texte d'introduction", blank=True)

    class Meta:
        verbose_name = "En-tête /témoignages/"
        verbose_name_plural = "En-tête /témoignages/"

    def __str__(self):
        return "En-tête /témoignages/"

    def clean(self):
        if not self.pk and TemoignagesPage.objects.exists():
            raise ValidationError("Un seul en-tête peut exister (singleton).")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY_TEMOIGNAGES_PAGE)

    @classmethod
    def get_solo(cls):
        obj = cache.get(CACHE_KEY_TEMOIGNAGES_PAGE)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(CACHE_KEY_TEMOIGNAGES_PAGE, obj, 300)
        return obj
