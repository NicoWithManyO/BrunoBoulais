from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.fields import RichTextField
from apps.core.models import TimestampedModel

CACHE_KEY = "site_parametres"


class Parametres(TimestampedModel):
    """Singleton holding global site settings editable by Bruno."""

    email_contact = models.EmailField("Email de contact", default="boulaisbruno@free.fr")
    telephone = models.CharField("Téléphone", max_length=30, blank=True)
    ville = models.CharField("Ville", max_length=100, blank=True, default="Misson (40)")

    texte_pied_de_page = RichTextField(
        "Texte du pied de page", blank=True,
        help_text="Quelques mots affichés dans le footer."
    )

    facebook_url = models.URLField("URL Facebook", blank=True)
    instagram_url = models.URLField("URL Instagram", blank=True)

    bandeau_actif = models.BooleanField(
        "Afficher le bandeau dédicace", default=False,
        help_text="Affiche un bandeau en haut du site annonçant la prochaine dédicace."
    )
    bandeau_texte = models.CharField("Texte du bandeau", max_length=200, blank=True)
    bandeau_url = models.URLField("Lien du bandeau", blank=True)

    class Meta:
        verbose_name = "Paramètres du site"
        verbose_name_plural = "Paramètres du site"

    def __str__(self):
        return "Paramètres du site"

    def clean(self):
        if not self.pk and Parametres.objects.exists():
            raise ValidationError("Un seul jeu de paramètres peut exister (singleton).")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY)

    @classmethod
    def get_solo(cls):
        obj = cache.get(CACHE_KEY)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(CACHE_KEY, obj, 300)
        return obj
