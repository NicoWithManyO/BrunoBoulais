from django.db import models
from django.urls import reverse

from apps.core.models import SeoMixin, TimestampedModel


class Page(TimestampedModel, SeoMixin):
    """A simple editorial page composed of ordered content blocks."""

    SLUG_HOME = "accueil"
    SLUG_LIVRE = "le-livre"
    SLUG_BERTIN = "jacques-bertin"
    SLUG_AUTEUR = "l-auteur"

    slug = models.SlugField("Identifiant", max_length=80, unique=True)
    title = models.CharField("Titre", max_length=200)
    subtitle = models.CharField("Sous-titre", max_length=300, blank=True)
    published = models.BooleanField("Publiée", default=True)

    class Meta:
        verbose_name = "Page"
        verbose_name_plural = "Pages"
        ordering = ["slug"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        if self.slug == self.SLUG_HOME:
            return reverse("pages:home")
        return reverse("pages:page", args=[self.slug])


class ContentBlock(TimestampedModel):
    """Ordered block of content inside a Page."""

    TYPE_TEXT = "text"
    TYPE_HEADING = "heading"
    TYPE_QUOTE = "quote"
    TYPE_IMAGE = "image"
    TYPE_SEPARATOR = "separator"
    TYPE_GALLERY = "gallery"

    TYPE_CHOICES = [
        (TYPE_HEADING, "Titre"),
        (TYPE_TEXT, "Texte"),
        (TYPE_QUOTE, "Citation"),
        (TYPE_IMAGE, "Image"),
        (TYPE_SEPARATOR, "Séparateur"),
        (TYPE_GALLERY, "Galerie"),
    ]

    page = models.ForeignKey(
        Page, related_name="blocks", on_delete=models.CASCADE, verbose_name="Page"
    )
    type = models.CharField("Type", max_length=20, choices=TYPE_CHOICES)
    position = models.PositiveIntegerField("Position", default=0)
    data = models.JSONField("Contenu", default=dict, blank=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Bloc de contenu"
        verbose_name_plural = "Blocs de contenu"

    def __str__(self):
        return f"{self.page.slug} · {self.get_type_display()} #{self.position}"
