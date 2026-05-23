from django.db import models
from taggit.managers import TaggableManager

from apps.core.models import TimestampedModel


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
    fichier = models.FileField("Fichier", upload_to="galerie/")
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
