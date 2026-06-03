from django.db import models
from django.db.models.signals import pre_delete

from apps.core.fields import RichTextField
from apps.core.models import (
    CarrouselSettingsMixin,
    OrderedImage,
    TimestampedModel,
    delete_image_file,
)
from apps.core.uploads import portraits_image_upload_to
from apps.core.validators import IMAGE_VALIDATORS


class Personne(TimestampedModel, CarrouselSettingsMixin):
    """Represents Jacques Bertin or Bruno Boulais."""

    ROLE_AUTEUR = "auteur"
    ROLE_SUJET = "sujet"
    ROLE_CHOICES = [
        (ROLE_AUTEUR, "Auteur du livre"),
        (ROLE_SUJET, "Sujet du livre"),
    ]

    role = models.CharField("Rôle", max_length=20, choices=ROLE_CHOICES, unique=True)
    nom = models.CharField("Nom complet", max_length=100)
    sous_titre = models.CharField(
        "Sous-titre", max_length=200, blank=True,
        help_text="Ex. 'Chanteur, poète, écrivain' ou 'Auteur, près de Dax'."
    )
    annee_naissance = models.PositiveSmallIntegerField("Année de naissance", null=True, blank=True)
    bio_courte = models.CharField(
        "Bio courte", max_length=300, blank=True,
        help_text="Pour les vignettes et le pied de page."
    )
    bio_longue = RichTextField(
        "Biographie", blank=True,
        help_text="Texte riche : gras, italique, sauts de ligne."
    )
    citation_texte = RichTextField(
        "Citation", blank=True, mode="inline",
        help_text="Phrase mise en exergue sur la page dédiée."
    )
    citation_auteur = models.CharField(
        "Auteur de la citation", max_length=120, blank=True,
    )
    citation_commentaire = models.CharField(
        "Commentaire", max_length=300, blank=True,
        help_text="Quelques mots, affichés sous l'auteur, sur la citation ou son auteur (optionnel)."
    )

    class Meta:
        verbose_name = "Personne"
        verbose_name_plural = "Personnes"

    def __str__(self):
        return self.nom


class PersonneImage(OrderedImage):
    """A portrait image attached to a Personne (1-N for carousel)."""

    personne = models.ForeignKey(
        Personne, related_name="images", on_delete=models.CASCADE,
        verbose_name="Personne",
    )
    image = models.ImageField(
        "Image", upload_to=portraits_image_upload_to, validators=IMAGE_VALIDATORS,
    )


pre_delete.connect(delete_image_file, sender=PersonneImage)
