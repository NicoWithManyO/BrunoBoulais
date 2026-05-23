"""ModelForms used by the custom /gestion/ admin interface."""
from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.forms import inlineformset_factory

from apps.actualites.models import Actualite, ActualiteImage, ActualitesPage
from apps.core.images import strip_exif
from apps.galerie.models import Media
from apps.livre.models import LienAchat, Livre, LivreImage
from apps.pages.models import Accueil, AccueilImage
from apps.parametres.models import Parametres
from apps.personnes.models import Personne, PersonneImage
from apps.temoignages.models import Temoignage, TemoignagesPage


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


def _make_image_formset(parent_model, image_model):
    """Build an inline formset for an OrderedImage subclass (image + alt + position).

    Shared between Actualite, Accueil, Personne, Livre: same fields, same
    StripExif behaviour, no extra blank rows (uploads happen via the
    `nouvelles_images` multi-file field handled in the view).
    """
    class _Form(StripExifMixin, forms.ModelForm):
        exif_fields = ["image"]

        class Meta:
            model = image_model
            fields = ["image", "alt", "legende", "position"]

    return inlineformset_factory(
        parent_model, image_model, form=_Form, extra=0, can_delete=True,
    )


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
            "delai_rotation_s",
        ]
        widgets = {
            "date_evenement": _DateInput(),
            "heure_debut": _TimeInput(),
            "heure_fin": _TimeInput(),
            "date_publication": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "chapo": forms.Textarea(attrs={"rows": 2}),
        }


ActualiteImageFormSet = _make_image_formset(Actualite, ActualiteImage)


class ActualitesPageForm(forms.ModelForm):
    class Meta:
        model = ActualitesPage
        fields = ["eyebrow", "titre", "intro"]


class TemoignageForm(forms.ModelForm):
    class Meta:
        model = Temoignage
        fields = ["auteur", "source", "texte", "statut", "mis_en_avant", "position"]


class TemoignagesPageForm(forms.ModelForm):
    class Meta:
        model = TemoignagesPage
        fields = ["eyebrow", "titre", "intro"]


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
            "delai_rotation_s",
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


LivreImageFormSet = _make_image_formset(Livre, LivreImage)


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
            "delai_rotation_s",
        ]
        widgets = {
            "bio_courte": forms.Textarea(attrs={"rows": 2}),
        }


PersonneImageFormSet = _make_image_formset(Personne, PersonneImage)


class AccueilForm(StripExifMixin, forms.ModelForm):
    exif_fields = ["og_image"]

    class Meta:
        model = Accueil
        fields = [
            "hero_titre", "hero_pitch",
            "pull_quote_texte", "pull_quote_auteur",
            "dedicaces_intro", "temoignages_intro",
            "delai_rotation_s",
            "seo_title", "seo_description", "og_image",
        ]
        widgets = {
            "seo_description": forms.Textarea(attrs={"rows": 2}),
        }


AccueilImageFormSet = _make_image_formset(Accueil, AccueilImage)
