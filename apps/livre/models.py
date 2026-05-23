from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimestampedModel
from apps.core.uploads import livre_upload_to
from apps.core.validators import IMAGE_VALIDATORS


class Livre(TimestampedModel):
    """Singleton model representing THE book."""

    titre = models.CharField("Titre", max_length=200, default="Jacques Bertin, le géant discret de la chanson")
    sous_titre = models.CharField("Sous-titre", max_length=200, blank=True)
    pitch_court = models.CharField(
        "Pitch court", max_length=300, blank=True,
        help_text="Une ou deux phrases d'accroche, visible sur la page d'accueil."
    )
    pitch_long = models.TextField(
        "Présentation longue", blank=True,
        help_text="Texte riche présentant le livre sur sa page dédiée (HTML autorisé)."
    )
    sommaire = models.TextField(
        "Sommaire", blank=True,
        help_text="Sommaire du livre (HTML autorisé)."
    )
    extrait = models.TextField(
        "Extrait", blank=True,
        help_text="Extrait choisi du livre (HTML autorisé)."
    )
    couverture = models.ImageField(
        "Couverture", upload_to=livre_upload_to, blank=True, null=True,
        validators=IMAGE_VALIDATORS,
    )
    isbn = models.CharField("ISBN", max_length=20, blank=True)
    editeur = models.CharField("Éditeur", max_length=100, default="Éditions du Petit Pavé")
    pages = models.PositiveIntegerField("Nombre de pages", null=True, blank=True)
    prix_euros = models.DecimalField(
        "Prix (€)", max_digits=6, decimal_places=2, null=True, blank=True
    )

    class Meta:
        verbose_name = "Livre"
        verbose_name_plural = "Livre"

    def __str__(self):
        return self.titre

    def clean(self):
        if not self.pk and Livre.objects.exists():
            raise ValidationError("Un seul livre peut exister (singleton).")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class LienAchat(TimestampedModel):
    """External purchase links for the book."""

    livre = models.ForeignKey(
        Livre, related_name="liens_achat", on_delete=models.CASCADE, verbose_name="Livre"
    )
    libelle = models.CharField("Libellé", max_length=100)
    url = models.URLField("Lien")
    description = models.CharField(
        "Description", max_length=200, blank=True,
        help_text="Optionnelle : ex. 'avec dédicace, envoi Mondial Relay'."
    )
    position = models.PositiveIntegerField("Position", default=0)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Lien d'achat"
        verbose_name_plural = "Liens d'achat"

    def __str__(self):
        return self.libelle
