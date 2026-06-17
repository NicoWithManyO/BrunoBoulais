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

    def _adresse_postale_required(self, cleaned):
        # Base : l'adresse est toujours requise pour une commande. Surchargeable
        # (CommandeForm ne l'exige qu'en livraison à domicile).
        return True

    def clean(self):
        cleaned = super().clean()
        sujet = cleaned.get("sujet")
        if sujet == Message.SUJET_COMMANDE:
            if not (cleaned.get("telephone") or "").strip():
                self.add_error("telephone", "Numéro de téléphone requis pour une commande.")
            if self._adresse_postale_required(cleaned) and not (cleaned.get("adresse_postale") or "").strip():
                self.add_error("adresse_postale", "Adresse de destination requise pour une commande.")
            if not cleaned.get("mode_paiement"):
                self.add_error("mode_paiement", "Merci d'indiquer un mode de paiement.")
        return cleaned

    def save_and_notify(self):
        msg = self.save()
        lines = [
            f"Réf. #{msg.pk}",
            f"De : {msg.nom} <{msg.email}>",
            f"Téléphone : {msg.telephone or '—'}",
            f"Adresse : {msg.adresse_postale or '—'}",
            f"Sujet : {msg.get_sujet_display()}",
            f"Paiement : {msg.get_mode_paiement_display() or '—'}",
        ]
        # Détails spécifiques à une commande (les champs livraison/dédicace
        # n'existent que via CommandeForm ; absents, on n'ajoute rien).
        if msg.sujet == Message.SUJET_COMMANDE:
            if msg.nb_exemplaires:
                produit = PRODUITS[msg.nb_exemplaires]
                lines.append(f"Exemplaires : {produit['label']}")
                lines.append(f"Montant : {montant_euros(produit['montant_cents'])}")
            lines.append("État : en attente de règlement")
            if msg.mode_livraison == Message.LIVRAISON_DOMICILE:
                lines.append(f"Livraison : Domicile — {msg.adresse_postale or '—'}")
            elif msg.mode_livraison:
                point = msg.point_relais_libelle or "(non précisé)"
                lines.append(
                    f"Livraison : {msg.get_mode_livraison_display()} — "
                    f"{point} (ID {msg.point_relais_id or '—'})"
                )
            if msg.dedicace:
                prenom = f" (prénom : {msg.prenom_dedicace})" if msg.prenom_dedicace else ""
                lines.append(f"Dédicace : oui{prenom}")
            else:
                lines.append("Dédicace : non")
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
        fields = ContactForm.Meta.fields + [
            "nb_exemplaires",
            "mode_livraison",
            "point_relais_id",
            "point_relais_libelle",
            "dedicace",
            "prenom_dedicace",
        ]
        widgets = {
            **ContactForm.Meta.widgets,
            # Renseignés par le widget Mondial Relay côté navigateur.
            "point_relais_id": forms.HiddenInput(),
            "point_relais_libelle": forms.HiddenInput(),
        }

    # Modes de livraison qui passent par un point Mondial Relay (vs domicile).
    _MODES_POINT = (Message.LIVRAISON_POINT_RELAIS, Message.LIVRAISON_LOCKER)

    def _adresse_postale_required(self, cleaned):
        # L'adresse libre n'est exigée qu'en livraison à domicile ; pour un point
        # relais/locker c'est `point_relais_id` qui fait foi (voir clean()).
        return cleaned.get("mode_livraison") == Message.LIVRAISON_DOMICILE

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("sujet") == Message.SUJET_COMMANDE:
            if not cleaned.get("nb_exemplaires"):
                self.add_error("nb_exemplaires", "Merci d'indiquer le nombre d'exemplaires.")
            mode_livraison = cleaned.get("mode_livraison")
            if not mode_livraison:
                self.add_error("mode_livraison", "Merci d'indiquer un mode de livraison.")
            elif mode_livraison in self._MODES_POINT and not cleaned.get("point_relais_id"):
                self.add_error("point_relais_id", "Merci de sélectionner un point relais sur la carte.")
        return cleaned
