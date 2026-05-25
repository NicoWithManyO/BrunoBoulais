"""ModelForms used by the custom /gestion/ admin interface."""
from pathlib import Path

from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.forms import inlineformset_factory
from django.utils import timezone

from apps.actualites.models import Actualite, ActualiteImage, ActualitesPage
from apps.carnet.models import Billet
from apps.contact.models import ContactPage
from apps.core.images import strip_exif
from apps.core.validators import ALLOWED_IMAGE_EXTENSIONS, ALLOWED_VIDEO_EXTENSIONS
from apps.discotheque.models import Chanson
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


# HTML5 <input type="date|time|datetime-local"> exchanges values in ISO format,
# but with LANGUAGE_CODE="fr-fr" Django's default DATE_INPUT_FORMATS expect
# "%d/%m/%Y" — so values neither render nor parse without these overrides.
class _DateInput(forms.DateInput):
    input_type = "date"
    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format="%Y-%m-%d")


class _TimeInput(forms.TimeInput):
    input_type = "time"
    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format="%H:%M")


class _DateTimeLocalInput(forms.DateTimeInput):
    input_type = "datetime-local"
    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format="%Y-%m-%dT%H:%M")

    def format_value(self, value):
        # USE_TZ=True stores values in UTC; HTML <input type="datetime-local">
        # has no timezone, so we must render in TIME_ZONE-local time.
        if value and hasattr(value, "tzinfo") and value.tzinfo is not None:
            value = timezone.localtime(value)
        return super().format_value(value)


_HTML5_DATE_FORMATS = ["%Y-%m-%d"]
_HTML5_TIME_FORMATS = ["%H:%M", "%H:%M:%S"]
_HTML5_DATETIME_FORMATS = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]


class ActualiteForm(forms.ModelForm):
    date_evenement = forms.DateField(
        label="Date de l'événement", required=False,
        help_text="Pour les dédicaces et événements.",
        widget=_DateInput(), input_formats=_HTML5_DATE_FORMATS,
    )
    heure_debut = forms.TimeField(
        label="Heure début", required=False, help_text="Facultatif.",
        widget=_TimeInput(), input_formats=_HTML5_TIME_FORMATS,
    )
    heure_fin = forms.TimeField(
        label="Heure fin", required=False, help_text="Facultatif.",
        widget=_TimeInput(), input_formats=_HTML5_TIME_FORMATS,
    )
    date_publication = forms.DateTimeField(
        label="Date/heure de publication", required=False,
        help_text="Si vide, la date d'enregistrement est utilisée.",
        widget=_DateTimeLocalInput(), input_formats=_HTML5_DATETIME_FORMATS,
    )

    def clean_date_publication(self):
        return self.cleaned_data.get("date_publication") or timezone.now()

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
            "chapo": forms.Textarea(attrs={"rows": 2}),
        }


ActualiteImageFormSet = _make_image_formset(Actualite, ActualiteImage)


class ActualitesPageForm(forms.ModelForm):
    class Meta:
        model = ActualitesPage
        fields = ["eyebrow", "titre", "intro"]


class BilletForm(forms.ModelForm):
    date_publication = forms.DateTimeField(
        label="Date/heure de publication", required=False,
        help_text="Si vide, la date d'enregistrement est utilisée.",
        widget=_DateTimeLocalInput(), input_formats=_HTML5_DATETIME_FORMATS,
    )

    def clean_date_publication(self):
        return self.cleaned_data.get("date_publication") or timezone.now()

    class Meta:
        model = Billet
        fields = ["titre", "statut", "date_publication", "contenu"]


class ChansonForm(StripExifMixin, forms.ModelForm):
    exif_fields = ["illustration"]

    class Meta:
        model = Chanson
        fields = [
            "titre", "url_youtube", "illustration",
            "description", "album", "annee",
            "position", "publie",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "description": "Avis de Bruno",
        }
        help_texts = {
            "description": "Affiché à côté du lecteur quand la chanson est sélectionnée.",
        }


class TemoignageForm(forms.ModelForm):
    class Meta:
        model = Temoignage
        fields = ["auteur", "source", "texte", "statut", "mis_en_avant", "position"]


class TemoignagesPageForm(forms.ModelForm):
    class Meta:
        model = TemoignagesPage
        fields = ["eyebrow", "titre", "intro"]


class ContactPageForm(forms.ModelForm):
    class Meta:
        model = ContactPage
        fields = [
            "eyebrow", "titre", "intro",
            "merci_eyebrow", "merci_titre", "merci_message",
        ]


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

    def clean(self):
        cleaned = super().clean()
        f = cleaned.get("fichier")
        type_ = cleaned.get("type")
        if isinstance(f, UploadedFile) and type_:
            ext = Path(f.name).suffix.lower().lstrip(".")
            if type_ == Media.TYPE_IMAGE and ext not in ALLOWED_IMAGE_EXTENSIONS:
                self.add_error("fichier", (
                    f"Extension « .{ext} » incompatible avec le type Image. "
                    f"Attendu : {', '.join(ALLOWED_IMAGE_EXTENSIONS)}."
                ))
            elif type_ == Media.TYPE_VIDEO and ext not in ALLOWED_VIDEO_EXTENSIONS:
                self.add_error("fichier", (
                    f"Extension « .{ext} » incompatible avec le type Vidéo. "
                    f"Attendu : {', '.join(ALLOWED_VIDEO_EXTENSIONS)}."
                ))
        return cleaned


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


class LienAchatForm(forms.ModelForm):
    """ModelForm for purchase links with one-touch deletion of emptied rows.

    Existing rows whose libellé AND url have both been cleared are treated as
    a delete intent: we set DELETE=True and drop the required-field errors
    that would otherwise block the whole save. Without this, an editor who
    blanks a row to remove it gets a required-field error and may not
    realize a "Supprimer ce lien" checkbox was needed.

    The url field is rendered as a plain <input type="text"> (not
    <input type="url">) so the browser's HTML5 validator doesn't reject
    bare hosts like "www.free.fr" before submit. Django's form URLField
    already auto-prepends "https://" via assume_scheme.
    """

    url = forms.URLField(
        label="Lien",
        max_length=200,
        assume_scheme="https",
        widget=forms.TextInput(attrs={"placeholder": "ex. www.editeur.fr"}),
    )

    class Meta:
        model = LienAchat
        fields = ["libelle", "url", "type", "description", "position"]

    def clean(self):
        super().clean()
        if (
            self.instance.pk
            and not (self.cleaned_data.get("libelle") or "").strip()
            and not (self.cleaned_data.get("url") or "").strip()
        ):
            self._errors = {}
            self.cleaned_data["DELETE"] = True
        return self.cleaned_data


LienAchatFormSet = inlineformset_factory(
    Livre,
    LienAchat,
    form=LienAchatForm,
    fields=["libelle", "url", "type", "description", "position"],
    extra=0,
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
