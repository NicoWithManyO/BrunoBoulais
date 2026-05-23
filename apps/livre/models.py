from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import pre_delete

from apps.core.fields import RichTextField
from apps.core.models import (
    CarrouselSettingsMixin,
    OrderedImage,
    TimestampedModel,
    delete_image_file,
)
from apps.core.uploads import livre_image_upload_to
from apps.core.validators import IMAGE_VALIDATORS


class Livre(TimestampedModel, CarrouselSettingsMixin):
    """Singleton model representing THE book."""

    titre = models.CharField("Titre", max_length=200, default="Jacques Bertin, le géant discret de la chanson")
    sous_titre = models.CharField("Sous-titre", max_length=200, blank=True)
    pitch_court = models.CharField(
        "Pitch court", max_length=300, blank=True,
        help_text="Une ou deux phrases d'accroche, visible sur la page d'accueil."
    )
    pitch_long = RichTextField(
        "Présentation longue", blank=True,
        help_text="Texte riche présentant le livre sur sa page dédiée."
    )
    sommaire = RichTextField(
        "Sommaire", blank=True,
        help_text="Sommaire du livre."
    )
    extrait = RichTextField(
        "Extrait", blank=True,
        help_text="Extrait choisi du livre."
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


class LivreImage(OrderedImage):
    """A cover/image attached to the Livre singleton (1-N for carousel)."""

    livre = models.ForeignKey(
        Livre, related_name="images", on_delete=models.CASCADE,
        verbose_name="Livre",
    )
    image = models.ImageField(
        "Image", upload_to=livre_image_upload_to, validators=IMAGE_VALIDATORS,
    )


pre_delete.connect(delete_image_file, sender=LivreImage)


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
