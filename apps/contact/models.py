from django.db import models

from apps.core.models import TimestampedModel


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
    sujet = models.CharField("Sujet", max_length=20, choices=SUJET_CHOICES, default=SUJET_QUESTION)
    contenu = models.TextField("Message")
    lu = models.BooleanField("Lu", default=False)
    archive = models.BooleanField("Archivé", default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Message"
        verbose_name_plural = "Messages"

    def __str__(self):
        return f"{self.nom} — {self.get_sujet_display()}"
