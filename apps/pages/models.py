from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from apps.core.models import SeoMixin, TimestampedModel

CACHE_KEY_ACCUEIL = "pages_accueil"


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


class Accueil(TimestampedModel, SeoMixin):
    """Singleton holding the editable content of the public home page."""

    hero_titre = models.TextField(
        "Titre du hero",
        blank=True,
        help_text=(
            "Titre principal de la page d'accueil. HTML autorisé : <em>…</em> "
            "pour l'accent terracotta, <br> pour les retours à la ligne."
        ),
    )
    hero_pitch = models.TextField(
        "Pitch du hero",
        blank=True,
        help_text="Paragraphe d'introduction sous le titre.",
    )
    hero_image = models.ImageField(
        "Image du hero",
        upload_to="accueil/",
        blank=True,
        null=True,
        help_text=(
            "Optionnelle. Si renseignée, remplace la couverture-placeholder à droite du titre."
        ),
    )

    pull_quote_texte = models.TextField(
        "Citation centrale",
        blank=True,
        help_text="Phrase mise en exergue entre le hero et les actualités.",
    )
    pull_quote_auteur = models.CharField(
        "Auteur de la citation",
        max_length=120,
        blank=True,
    )

    dedicaces_intro = models.TextField(
        "Introduction du bloc Dédicaces",
        blank=True,
        help_text="Texte sous le titre « Dédicaces & actualités ».",
    )
    temoignages_intro = models.TextField(
        "Introduction du bloc Témoignages",
        blank=True,
        help_text="Texte affiché au-dessus du carrousel de témoignages (optionnel).",
    )

    class Meta:
        verbose_name = "Page d'accueil"
        verbose_name_plural = "Page d'accueil"

    def __str__(self):
        return "Page d'accueil"

    def clean(self):
        if not self.pk and Accueil.objects.exists():
            raise ValidationError("Une seule page d'accueil peut exister (singleton).")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY_ACCUEIL)

    @classmethod
    def get_solo(cls):
        obj = cache.get(CACHE_KEY_ACCUEIL)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(CACHE_KEY_ACCUEIL, obj, 300)
        return obj
