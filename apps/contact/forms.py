import logging

from django import forms
from django.conf import settings
from django.core.mail import EmailMessage

from .models import Message

logger = logging.getLogger(__name__)


class ContactForm(forms.ModelForm):
    """Public contact form with honeypot anti-spam."""

    # Champ honeypot : caché en CSS, doit rester vide
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "hp-field", "tabindex": "-1", "autocomplete": "off"}),
        label="",
    )

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Spam détecté.")
        return ""

    class Meta:
        model = Message
        fields = ["nom", "email", "telephone", "sujet", "contenu"]
        widgets = {
            "contenu": forms.Textarea(attrs={"rows": 6}),
        }

    def save_and_notify(self):
        msg = self.save()
        email = EmailMessage(
            subject=f"[brunoboulais.fr] {msg.get_sujet_display()} — {msg.nom}",
            body=(
                f"De : {msg.nom} <{msg.email}>\n"
                f"Téléphone : {msg.telephone or '—'}\n"
                f"Sujet : {msg.get_sujet_display()}\n\n"
                f"{msg.contenu}\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.CONTACT_EMAIL],
            reply_to=[msg.email],
        )
        try:
            email.send(fail_silently=False)
        except Exception:
            logger.exception("Contact form notification failed for message #%s", msg.pk)
        return msg
