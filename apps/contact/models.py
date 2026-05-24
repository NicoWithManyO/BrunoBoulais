from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.fields import RichTextField
from apps.core.models import TimestampedModel

CACHE_KEY_CONTACT_PAGE = "contact_page"


class ContactPage(TimestampedModel):
    """Singleton holding the editable header of /contact/ AND the post-submit /contact/merci/ page."""

    eyebrow = models.CharField("Surtitre", max_length=80, blank=True)
    titre = models.CharField("Titre", max_length=120, blank=True)
    intro = RichTextField("Texte d'introduction", blank=True)
    merci_eyebrow = models.CharField("Surtitre (page Merci)", max_length=80, blank=True)
    merci_titre = models.CharField("Titre (page Merci)", max_length=120, blank=True)
    merci_message = RichTextField("Message de remerciement", mode="inline", blank=True)

    class Meta:
        verbose_name = "Page /contact/"
        verbose_name_plural = "Page /contact/"

    def __str__(self):
        return "Page /contact/"

    def clean(self):
        if not self.pk and ContactPage.objects.exists():
            raise ValidationError("Un seul en-tête peut exister (singleton).")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY_CONTACT_PAGE)

    @classmethod
    def get_solo(cls):
        obj = cache.get(CACHE_KEY_CONTACT_PAGE)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(CACHE_KEY_CONTACT_PAGE, obj, 300)
        return obj


class Message(TimestampedModel):
    """A message sent through the public contact form."""

    SUJET_COMMANDE = "commande"
    SUJET_QUESTION = "question"
    SUJET_PRESSE = "presse"
    SUJET_AUTRE = "autre"
    SUJET_CHOICES = [
        (SUJET_COMMANDE, "Commande dédicacée"),
        (SUJET_QUESTION, "Question"),
        (SUJET_PRESSE, "Demande presse"),
        (SUJET_AUTRE, "Autre"),
    ]

    nom = models.CharField("Nom", max_length=120)
    email = models.EmailField("Email")
    telephone = models.CharField("Téléphone", max_length=30, blank=True)
    adresse_postale = models.TextField("Adresse postale de destination", blank=True)
    sujet = models.CharField("Sujet", max_length=20, choices=SUJET_CHOICES, default=SUJET_COMMANDE)
    contenu = models.TextField("Message")
    lu = models.BooleanField("Lu", default=False)
    archive = models.BooleanField("Archivé", default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Message"
        verbose_name_plural = "Messages"

    def __str__(self):
        return f"{self.nom} — {self.get_sujet_display()}"
