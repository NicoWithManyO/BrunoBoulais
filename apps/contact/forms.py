import logging

from django import forms
from django.conf import settings
from django.core.mail import EmailMessage

from .models import PRODUITS, Message, montant_euros

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
        fields = ["nom", "sujet", "email", "telephone", "adresse_postale", "mode_paiement", "contenu"]
        widgets = {
            "contenu": forms.Textarea(attrs={"rows": 6}),
            "adresse_postale": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        sujet = cleaned.get("sujet")
        if sujet == Message.SUJET_COMMANDE:
            if not (cleaned.get("telephone") or "").strip():
                self.add_error("telephone", "Numéro de téléphone requis pour une commande.")
            if not (cleaned.get("adresse_postale") or "").strip():
                self.add_error("adresse_postale", "Adresse de destination requise pour une commande.")
            if not cleaned.get("mode_paiement"):
                self.add_error("mode_paiement", "Merci d'indiquer un mode de paiement.")
        return cleaned

    def save_and_notify(self):
        msg = self.save()
        # Ligne quantité + montant uniquement si renseignée (commande).
        exemplaires_line = ""
        if msg.nb_exemplaires:
            produit = PRODUITS[msg.nb_exemplaires]
            exemplaires_line = (
                f"Exemplaires : {produit['label']} — "
                f"{montant_euros(produit['montant_cents'])}\n"
            )
        email = EmailMessage(
            subject=f"[jacques-bertin.manyo.dev] {msg.get_sujet_display()} — {msg.nom}",
            body=(
                f"De : {msg.nom} <{msg.email}>\n"
                f"Téléphone : {msg.telephone or '—'}\n"
                f"Adresse : {msg.adresse_postale or '—'}\n"
                f"Sujet : {msg.get_sujet_display()}\n"
                f"Paiement : {msg.get_mode_paiement_display() or '—'}\n"
                f"{exemplaires_line}\n"
                f"{msg.contenu}\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.CONTACT_EMAIL],
            reply_to=[msg.email],
        )
        try:
            # msg.notified vaut déjà True par défaut : pas de réécriture sur le
            # chemin nominal.
            email.send(fail_silently=False)
        except Exception:
            # La commande est déjà enregistrée (source de vérité = admin gestion) :
            # on n'échoue pas la requête pour un mail. On persiste le drapeau pour
            # que la commande remonte comme « à traiter » dans l'admin, + log.
            msg.notified = False
            msg.save(update_fields=["notified"])
            logger.error(
                "Contact: commande #%s de %s <%s> enregistrée mais notification "
                "non envoyée — à traiter manuellement.",
                msg.pk,
                msg.nom,
                msg.email,
                exc_info=True,
            )
        return msg


class CommandeForm(ContactForm):
    """Formulaire de la nouvelle page de commande : ajoute le nombre d'exemplaires.

    Sous-classe pour ne pas toucher ``ContactForm`` (encore utilisé par la page
    /contact/ live) tant que le swap n'est pas fait.
    """

    class Meta(ContactForm.Meta):
        fields = ContactForm.Meta.fields + ["nb_exemplaires"]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("sujet") == Message.SUJET_COMMANDE and not cleaned.get("nb_exemplaires"):
            self.add_error("nb_exemplaires", "Merci d'indiquer le nombre d'exemplaires.")
        return cleaned
