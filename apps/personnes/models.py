from django.db import models

from apps.core.fields import RichTextField
from apps.core.models import TimestampedModel
from apps.core.uploads import portraits_upload_to
from apps.core.validators import IMAGE_VALIDATORS


class Personne(TimestampedModel):
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
    portrait = models.ImageField(
        "Portrait", upload_to=portraits_upload_to, blank=True, null=True,
        validators=IMAGE_VALIDATORS,
    )

    class Meta:
        verbose_name = "Personne"
        verbose_name_plural = "Personnes"

    def __str__(self):
        return self.nom
