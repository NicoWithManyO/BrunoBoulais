"""ModelForms used by the custom /gestion/ admin interface."""
from django import forms
from django.forms import inlineformset_factory

from apps.actualites.models import Actualite
from apps.galerie.models import Media
from apps.livre.models import LienAchat, Livre
from apps.pages.models import Accueil
from apps.parametres.models import Parametres
from apps.personnes.models import Personne
from apps.temoignages.models import Temoignage


class _DateInput(forms.DateInput):
    input_type = "date"


class _TimeInput(forms.TimeInput):
    input_type = "time"


class ActualiteForm(forms.ModelForm):
    class Meta:
        model = Actualite
        fields = [
            "titre", "type", "statut",
            "date_evenement", "heure_debut", "heure_fin",
            "lieu", "ville",
            "chapo", "contenu", "image",
            "date_publication",
        ]
        widgets = {
            "date_evenement": _DateInput(),
            "heure_debut": _TimeInput(),
            "heure_fin": _TimeInput(),
            "date_publication": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "chapo": forms.Textarea(attrs={"rows": 2}),
            "contenu": forms.Textarea(attrs={"rows": 8}),
        }


class TemoignageForm(forms.ModelForm):
    class Meta:
        model = Temoignage
        fields = ["auteur", "source", "texte", "statut", "mis_en_avant", "position"]
        widgets = {
            "texte": forms.Textarea(attrs={"rows": 5}),
        }


class MediaForm(forms.ModelForm):
    class Meta:
        model = Media
        fields = ["fichier", "type", "categorie", "legende", "alt", "position", "publie"]


class LivreForm(forms.ModelForm):
    class Meta:
        model = Livre
        fields = [
            "titre", "sous_titre", "pitch_court", "pitch_long",
            "sommaire", "extrait", "couverture",
            "isbn", "editeur", "pages", "prix_euros",
        ]
        widgets = {
            "pitch_court": forms.Textarea(attrs={"rows": 2}),
            "pitch_long": forms.Textarea(attrs={"rows": 8}),
            "sommaire": forms.Textarea(attrs={"rows": 6}),
            "extrait": forms.Textarea(attrs={"rows": 6}),
        }


LienAchatFormSet = inlineformset_factory(
    Livre,
    LienAchat,
    fields=["libelle", "url", "description", "position"],
    extra=1,
    can_delete=True,
)


class ParametresForm(forms.ModelForm):
    class Meta:
        model = Parametres
        fields = [
            "email_contact", "telephone", "ville",
            "texte_pied_de_page",
            "facebook_url", "instagram_url",
            "bandeau_actif", "bandeau_texte", "bandeau_url",
        ]
        widgets = {
            "texte_pied_de_page": forms.Textarea(attrs={"rows": 3}),
        }


class PersonneForm(forms.ModelForm):
    class Meta:
        model = Personne
        fields = [
            "nom", "sous_titre", "annee_naissance",
            "bio_courte", "bio_longue", "portrait",
        ]
        widgets = {
            "bio_courte": forms.Textarea(attrs={"rows": 2}),
            "bio_longue": forms.Textarea(attrs={"rows": 12}),
        }


class AccueilForm(forms.ModelForm):
    class Meta:
        model = Accueil
        fields = [
            "hero_titre", "hero_pitch", "hero_image",
            "pull_quote_texte", "pull_quote_auteur",
            "dedicaces_intro", "temoignages_intro",
            "seo_title", "seo_description", "og_image",
        ]
        widgets = {
            "hero_titre": forms.Textarea(attrs={"rows": 3}),
            "hero_pitch": forms.Textarea(attrs={"rows": 5}),
            "pull_quote_texte": forms.Textarea(attrs={"rows": 3}),
            "dedicaces_intro": forms.Textarea(attrs={"rows": 3}),
            "temoignages_intro": forms.Textarea(attrs={"rows": 3}),
            "seo_description": forms.Textarea(attrs={"rows": 2}),
        }
