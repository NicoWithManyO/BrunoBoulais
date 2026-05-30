from django.db import models
from django.db.models.signals import pre_delete
from django.utils import timezone
from django.utils.text import slugify

from apps.core.fields import RichTextField
from apps.core.models import OrderedImage, TimestampedModel, delete_image_file
from apps.core.uploads import carnet_contenu_upload_to
from apps.core.validators import IMAGE_VALIDATORS


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


class BilletImageContenu(OrderedImage):
    """Images insérables dans le corps du texte via le repère `[image:N]`.

    Affichées uniquement là où l'éditeur place leur repère dans le contenu.
    """

    LARGEUR_CHOICES = [
        ("100", "Pleine largeur"),
        ("75", "3/4 de la largeur"),
        ("50", "Moitié"),
        ("33", "Tiers"),
        ("25", "Quart"),
    ]
    ALIGNEMENT_CHOICES = [
        ("center", "Centré"),
        ("left", "À gauche (texte autour)"),
        ("right", "À droite (texte autour)"),
    ]

    billet = models.ForeignKey(
        Billet, related_name="images_contenu", on_delete=models.CASCADE,
        verbose_name="Billet",
    )
    image = models.ImageField(
        "Image", upload_to=carnet_contenu_upload_to, validators=IMAGE_VALIDATORS,
    )
    largeur = models.CharField(
        "Largeur", max_length=3, choices=LARGEUR_CHOICES, default="100",
        help_text="Proportion de la largeur du bloc occupée par l'image. Le ratio est conservé.",
    )
    alignement = models.CharField(
        "Alignement", max_length=6, choices=ALIGNEMENT_CHOICES, default="center",
        help_text="Position de l'image. À gauche ou à droite, le texte s'enroule autour "
                  "(sauf si « Pas de texte à côté » est coché).",
    )
    sans_habillage = models.BooleanField(
        "Pas de texte à côté", default=False,
        help_text="L'image reste seule sur sa ligne, à sa largeur : le texte ne "
                  "s'enroule pas autour. Sans effet sur une image centrée.",
    )


pre_delete.connect(delete_image_file, sender=BilletImageContenu)
