import logging

from django import forms
from django.conf import settings
from django.core.mail import EmailMessage

from .models import Message

logger = logging.getLogger(__name__)

# Sujets proposés dans le formulaire public. On EXCLUT SUJET_COMMANDE : la prise
# de commande a migré sur /boutique/. Le choix reste néanmoins dans
# Message.SUJET_CHOICES pour que get_sujet_display() rende encore les anciennes
# commandes en gestion.
SUJETS_CONTACT = [
    (v, l) for v, l in Message.SUJET_CHOICES if v != Message.SUJET_COMMANDE
]


class ContactForm(forms.ModelForm):
    """Public contact form with honeypot anti-spam."""

    # Champ honeypot : caché en CSS, doit rester vide
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "hp-field", "tabindex": "-1", "autocomplete": "off"}),
        label="",
    )

    class Meta:
        model = Message
        fields = ["nom", "sujet", "email", "telephone", "contenu"]
        widgets = {
            "contenu": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Placeholder explicite en tête : aucun sujet présélectionné.
        self.fields["sujet"].choices = [("", "Choisissez un sujet"), *SUJETS_CONTACT]

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Spam détecté.")
        return ""

    def save_and_notify(self):
        msg = self.save()
        lines = [
            f"Réf. #{msg.pk}",
            f"De : {msg.nom} <{msg.email}>",
            f"Téléphone : {msg.telephone or '—'}",
            f"Sujet : {msg.get_sujet_display()}",
        ]
        email = EmailMessage(
            subject=f"[jacques-bertin.manyo.dev] {msg.get_sujet_display()} — {msg.nom}",
            body="\n".join(lines) + f"\n\n{msg.contenu}\n",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.CONTACT_EMAIL],
            reply_to=[msg.email],
        )
        try:
            # msg.notified vaut déjà True par défaut : pas de réécriture sur le
            # chemin nominal.
            email.send(fail_silently=False)
        except Exception:
            # Le message est déjà enregistré (source de vérité = admin gestion) :
            # on n'échoue pas la requête pour un mail. On persiste le drapeau pour
            # que le message remonte comme « à traiter » dans l'admin, + log.
            msg.notified = False
            msg.save(update_fields=["notified"])
            logger.error(
                "Contact: message #%s de %s <%s> enregistré mais notification "
                "non envoyée — à traiter manuellement.",
                msg.pk,
                msg.nom,
                msg.email,
                exc_info=True,
            )
        return msg
