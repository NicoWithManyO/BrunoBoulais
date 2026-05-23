"""ModelForms used by the custom /gestion/ admin interface."""
from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.forms import inlineformset_factory

from apps.actualites.models import Actualite, ActualiteImage
from apps.core.images import strip_exif
from apps.galerie.models import Media
from apps.livre.models import LienAchat, Livre, LivreImage
from apps.pages.models import Accueil, AccueilImage
from apps.parametres.models import Parametres
from apps.personnes.models import Personne, PersonneImage
from apps.temoignages.models import Temoignage


class StripExifMixin:
    """Re-encodes any newly-uploaded image fields without their EXIF metadata.

    Subclass ModelForms set `exif_fields = [...]` to opt in. The mixin only
    touches fields that received a fresh upload — existing stored images on
    edit are left alone. Override `exif_fields_for(cleaned)` if a field is
    only an image conditionally (see MediaForm).
    """

    exif_fields: list[str] = []

    def exif_fields_for(self, cleaned):
        return self.exif_fields

    def clean(self):
        cleaned = super().clean()
        for fname in self.exif_fields_for(cleaned):
            f = cleaned.get(fname)
            if isinstance(f, UploadedFile):
                cleaned[fname] = strip_exif(f)
        return cleaned


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
            "chapo", "contenu",
            "date_publication",
        ]
        widgets = {
            "date_evenement": _DateInput(),
            "heure_debut": _TimeInput(),
            "heure_fin": _TimeInput(),
            "date_publication": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "chapo": forms.Textarea(attrs={"rows": 2}),
        }


class _ActualiteImageForm(StripExifMixin, forms.ModelForm):
    """Inline form for an existing ActualiteImage: thumbnail + alt + position + delete."""
    exif_fields = ["image"]

    class Meta:
        model = ActualiteImage
        fields = ["image", "alt", "position"]


ActualiteImageFormSet = inlineformset_factory(
    Actualite, ActualiteImage,
    form=_ActualiteImageForm,
    extra=0,
    can_delete=True,
)


class TemoignageForm(forms.ModelForm):
    class Meta:
        model = Temoignage
        fields = ["auteur", "source", "texte", "statut", "mis_en_avant", "position"]


class MediaForm(StripExifMixin, forms.ModelForm):
    exif_fields = ["fichier"]

    class Meta:
        model = Media
        fields = ["fichier", "type", "categorie", "legende", "alt", "position", "publie"]

    def exif_fields_for(self, cleaned):
        # MediaForm holds both images and videos; only strip if type=image.
        if cleaned.get("type") == Media.TYPE_IMAGE:
            return self.exif_fields
        return []


class LivreForm(forms.ModelForm):
    class Meta:
        model = Livre
        fields = [
            "titre", "sous_titre", "pitch_court", "pitch_long",
            "sommaire", "extrait",
            "isbn", "editeur", "pages", "prix_euros",
        ]
        widgets = {
            "pitch_court": forms.Textarea(attrs={"rows": 2}),
        }


LienAchatFormSet = inlineformset_factory(
    Livre,
    LienAchat,
    fields=["libelle", "url", "description", "position"],
    extra=1,
    can_delete=True,
)


class _LivreImageForm(StripExifMixin, forms.ModelForm):
    exif_fields = ["image"]

    class Meta:
        model = LivreImage
        fields = ["image", "alt", "position"]


LivreImageFormSet = inlineformset_factory(
    Livre, LivreImage,
    form=_LivreImageForm,
    extra=0,
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


class PersonneForm(forms.ModelForm):
    class Meta:
        model = Personne
        fields = [
            "nom", "sous_titre", "annee_naissance",
            "bio_courte", "bio_longue",
        ]
        widgets = {
            "bio_courte": forms.Textarea(attrs={"rows": 2}),
        }


class _PersonneImageForm(StripExifMixin, forms.ModelForm):
    exif_fields = ["image"]

    class Meta:
        model = PersonneImage
        fields = ["image", "alt", "position"]


PersonneImageFormSet = inlineformset_factory(
    Personne, PersonneImage,
    form=_PersonneImageForm,
    extra=0,
    can_delete=True,
)


class AccueilForm(StripExifMixin, forms.ModelForm):
    exif_fields = ["og_image"]

    class Meta:
        model = Accueil
        fields = [
            "hero_titre", "hero_pitch",
            "pull_quote_texte", "pull_quote_auteur",
            "dedicaces_intro", "temoignages_intro",
            "seo_title", "seo_description", "og_image",
        ]
        widgets = {
            "seo_description": forms.Textarea(attrs={"rows": 2}),
        }


class _AccueilImageForm(StripExifMixin, forms.ModelForm):
    exif_fields = ["image"]

    class Meta:
        model = AccueilImage
        fields = ["image", "alt", "position"]


AccueilImageFormSet = inlineformset_factory(
    Accueil, AccueilImage,
    form=_AccueilImageForm,
    extra=0,
    can_delete=True,
)
