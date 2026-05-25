import re

from django.db import models

from apps.core.models import TimestampedModel
from apps.core.uploads import discotheque_upload_to
from apps.core.validators import IMAGE_VALIDATORS

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
    """Chanson de Jacques Bertin présentée via un embed YouTube."""

    titre = models.CharField("Titre", max_length=200, blank=True)
    url_youtube = models.URLField("Lien YouTube", max_length=300)
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
        ordering = ["position", "-created_at"]
        verbose_name = "Chanson"
        verbose_name_plural = "Chansons"

    def __str__(self):
        return self.titre or self.url_youtube

    @property
    def youtube_id(self):
        return extract_youtube_id(self.url_youtube)
