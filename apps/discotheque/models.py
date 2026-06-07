import re

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, IntegerField, Value, When

from apps.core.fields import RichTextField
from apps.core.models import TimestampedModel
from apps.core.uploads import discotheque_audio_upload_to, discotheque_upload_to
from apps.core.validators import AUDIO_VALIDATORS, IMAGE_VALIDATORS

CACHE_KEY_DISCOTHEQUE_PAGE = "discotheque_page"

# Capture l'ID YouTube (11 caractères [A-Za-z0-9_-]) dans les formats d'URL
# courants : youtu.be/<id>, youtube.com/watch?v=<id>, /embed/<id>, /shorts/<id>.
# Les paramètres de query (&t=42s, ?si=…) sont ignorés grâce au quantifieur
# strict {11}.
_YOUTUBE_ID_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/|v/))"
    r"([A-Za-z0-9_-]{11})"
)


def extract_youtube_id(url):
    """Retourne l'ID vidéo YouTube extrait de `url`, ou None si introuvable."""
    if not url:
        return None
    match = _YOUTUBE_ID_RE.search(url)
    return match.group(1) if match else None


class Chanson(TimestampedModel):
    """Entrée de la discothèque : soit une chanson (embed YouTube), soit un
    enregistrement téléphonique (fichier audio uploadé), selon `type`."""

    TYPE_CHANSON = "chanson"
    TYPE_ENREGISTREMENT = "enregistrement"
    TYPE_CHOICES = [
        (TYPE_CHANSON, "Chanson (YouTube)"),
        (TYPE_ENREGISTREMENT, "Enregistrement téléphonique"),
    ]

    type = models.CharField(
        "Type", max_length=20, choices=TYPE_CHOICES, default=TYPE_CHANSON
    )
    titre = models.CharField("Titre", max_length=200, blank=True)
    url_youtube = models.URLField("Lien YouTube", max_length=300, blank=True)
    audio = models.FileField(
        "Fichier audio",
        upload_to=discotheque_audio_upload_to,
        validators=AUDIO_VALIDATORS,
        blank=True,
    )
    date_enregistrement = models.DateField("Date de l'enregistrement", null=True, blank=True)
    illustration = models.ImageField(
        "Illustration",
        upload_to=discotheque_upload_to,
        validators=IMAGE_VALIDATORS,
        blank=True,
    )
    description = models.TextField("Description", blank=True)
    album = models.CharField("Album", max_length=200, blank=True)
    annee = models.PositiveSmallIntegerField("Année", null=True, blank=True)
    position = models.PositiveIntegerField("Position", default=0)
    publie = models.BooleanField("Publié", default=True)

    class Meta:
        # Position > 0 prime (ordre manuel ascendant) ; position = 0 (défaut) =
        # « pas d'ordre choisi » → reléguée derrière, plus récente d'abord.
        ordering = [
            Case(
                When(position=0, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            ),
            "position",
            "-created_at",
        ]
        verbose_name = "Chanson"
        verbose_name_plural = "Chansons"

    def __str__(self):
        return self.titre or self.url_youtube or "Enregistrement"

    def clean(self):
        # Selon le type, le « contenu » obligatoire diffère : lien YouTube pour
        # une chanson, fichier audio pour un enregistrement.
        if self.type == self.TYPE_CHANSON and not self.url_youtube:
            raise ValidationError({"url_youtube": "Un lien YouTube est requis pour une chanson."})
        if self.type == self.TYPE_ENREGISTREMENT and not self.audio:
            raise ValidationError({"audio": "Un fichier audio est requis pour un enregistrement."})

    @property
    def est_enregistrement(self):
        return self.type == self.TYPE_ENREGISTREMENT

    @property
    def youtube_id(self):
        return extract_youtube_id(self.url_youtube)

    @property
    def is_playable(self):
        # Le « contenu lisible » dépend du type : audio pour un enregistrement,
        # ID YouTube extractible pour une chanson. Sert de garde côté template
        # pour ne pas rendre une carte morte (ni évaluer audio.url sur un champ
        # vide).
        return bool(self.audio) if self.est_enregistrement else bool(self.youtube_id)


class DiscothequePage(TimestampedModel):
    """Singleton holding the editable header of the public /discotheque/ page."""

    eyebrow = models.CharField("Surtitre", max_length=80, blank=True)
    titre = models.CharField("Titre", max_length=120, blank=True)
    intro = RichTextField("Texte d'introduction", blank=True)

    class Meta:
        verbose_name = "En-tête /discotheque/"
        verbose_name_plural = "En-tête /discotheque/"

    def __str__(self):
        return "En-tête /discotheque/"

    def clean(self):
        if not self.pk and DiscothequePage.objects.exists():
            raise ValidationError("Un seul en-tête peut exister (singleton).")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY_DISCOTHEQUE_PAGE)

    @classmethod
    def get_solo(cls):
        obj = cache.get(CACHE_KEY_DISCOTHEQUE_PAGE)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(CACHE_KEY_DISCOTHEQUE_PAGE, obj, 300)
        return obj
