from django import forms

from .models import Commande

# CB (Stripe) branchée à l'étape suivante : pour l'instant on n'expose que les
# modes de paiement réglables à la main (chèque/virement).
_PAIEMENT_CHOICES_HORS_CB = [
    (valeur, libelle)
    for valeur, libelle in Commande.PAIEMENT_CHOICES
    if valeur != Commande.PAIEMENT_CB
]


class CommandeForm(forms.ModelForm):
    """Coordonnées + livraison + paiement de la commande passée depuis le chapeau.

    Les articles viennent du chapeau (session), pas du formulaire : on ne
    saisit ici que le destinataire, le mode de livraison et le règlement.
    """

    # Champ honeypot : caché en CSS, doit rester vide.
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "hp-field", "tabindex": "-1", "autocomplete": "off"}),
        label="",
    )

    class Meta:
        model = Commande
        fields = [
            "nom",
            "email",
            "telephone",
            "adresse_postale",
            "mode_livraison",
            "point_relais_id",
            "point_relais_libelle",
            "mode_paiement",
            "dedicace",
            "prenom_dedicace",
        ]
        widgets = {
            "adresse_postale": forms.Textarea(attrs={"rows": 3}),
            # Renseignés par le widget Mondial Relay côté navigateur.
            "point_relais_id": forms.HiddenInput(),
            "point_relais_libelle": forms.HiddenInput(),
        }

    def __init__(self, *args, dedicacable=False, **kwargs):
        super().__init__(*args, **kwargs)
        # La dédicace n'a de sens que si un produit dédicaçable est au chapeau.
        self.dedicacable = dedicacable
        self.fields["mode_livraison"].choices = [
            ("", "Sélectionner un mode de livraison"),
            *Commande.LIVRAISON_CHOICES,
        ]
        self.fields["mode_paiement"].choices = [
            ("", "Sélectionner un mode de paiement"),
            *_PAIEMENT_CHOICES_HORS_CB,
        ]

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Spam détecté.")
        return ""

    def clean(self):
        cleaned = super().clean()
        # Téléphone + adresse destinataire requis : Mondial Relay les exige pour
        # l'envoi, même en point relais/locker.
        if not (cleaned.get("telephone") or "").strip():
            self.add_error("telephone", "Numéro de téléphone requis pour la livraison.")
        if not (cleaned.get("adresse_postale") or "").strip():
            self.add_error("adresse_postale", "Adresse de destination requise.")
        mode_livraison = cleaned.get("mode_livraison")
        if not mode_livraison:
            self.add_error("mode_livraison", "Merci d'indiquer un mode de livraison.")
        elif mode_livraison != Commande.LIVRAISON_POINT_RELAIS:
            # Hors point relais : pas de point à conserver, sinon un id fantôme
            # persiste quand on bascule relais → domicile.
            cleaned["point_relais_id"] = ""
            cleaned["point_relais_libelle"] = ""
        if not cleaned.get("mode_paiement"):
            self.add_error("mode_paiement", "Merci d'indiquer un mode de paiement.")
        # Dédicace : purgée si aucun produit dédiçaçable (pas de dédicace fantôme).
        if not self.dedicacable:
            cleaned["dedicace"] = False
            cleaned["prenom_dedicace"] = ""
        return cleaned
