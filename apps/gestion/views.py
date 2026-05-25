"""Custom backoffice for Bruno — replaces Django admin with a softer UX."""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST


def gestion_required(view_func):
    """Require an authenticated staff user; redirect to /gestion/connexion/ otherwise."""
    check = user_passes_test(
        lambda u: u.is_authenticated and u.is_staff,
        login_url="/gestion/connexion/",
    )

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        return check(view_func)(request, *args, **kwargs)

    return wrapped

from django.core.exceptions import ValidationError
from django.db.models import Max

from apps.actualites.models import Actualite, ActualiteImage, ActualitesPage
from apps.carnet.models import Billet
from apps.contact.models import ContactPage, Message
from apps.core.images import strip_exif
from apps.core.validators import IMAGE_VALIDATORS
from apps.discotheque.models import Chanson, DiscothequePage
from apps.galerie.models import GaleriePage, Media
from apps.livre.models import Livre, LivreImage
from apps.pages.models import Accueil, AccueilImage, Page
from apps.parametres.models import Parametres
from apps.personnes.models import Personne, PersonneImage
from apps.temoignages.models import Temoignage, TemoignagesPage

from .forms import (
    AccueilForm,
    AccueilImageFormSet,
    ActualiteForm,
    ActualiteImageFormSet,
    ActualitesPageForm,
    BilletForm,
    ChansonForm,
    ContactPageForm,
    DiscothequePageForm,
    GaleriePageForm,
    LienAchatFormSet,
    LivreForm,
    LivreImageFormSet,
    MediaForm,
    ParametresForm,
    PersonneForm,
    PersonneImageFormSet,
    TemoignageForm,
    TemoignagesPageForm,
)


# ---- Helpers for multi-image upload field shared across editors -------------

def _validate_new_images(request):
    """Validate files dropped into the shared `nouvelles_images` field.

    Returns (files, errors) — caller persists the files post-parent-save.
    Errors are prefixed with the offending filename so the user knows which
    file in a multi-upload batch was rejected.
    """
    files = request.FILES.getlist("nouvelles_images") if request.method == "POST" else []
    errors = []
    for f in files:
        for validator in IMAGE_VALIDATORS:
            try:
                validator(f)
            except ValidationError as e:
                for msg in e.messages:
                    errors.append(f"« {f.name} » : {msg}")
    return files, errors


def _flash_save_blocked(request, files):
    """Emit framework messages after a failed POST that re-renders the form.

    File inputs cannot be restored by the browser between requests, so any
    files the user selected are lost on re-render — we warn them explicitly.
    """
    if files:
        messages.warning(
            request,
            "Les images sélectionnées ont été perdues suite à l'erreur — "
            "merci de les re-sélectionner avant de cliquer à nouveau sur Enregistrer.",
        )
    messages.error(
        request,
        "Aucune modification n'a été enregistrée. Corrigez les erreurs "
        "ci-dessous puis cliquez à nouveau sur Enregistrer.",
    )


def _save_new_images(parent, files):
    """Create one image row per file at the next available `position`.

    Relies on the reverse manager `parent.images` (every OrderedImage
    subclass uses `related_name="images"`).
    """
    if not files:
        return
    max_pos = parent.images.aggregate(Max("position"))["position__max"] or 0
    for i, f in enumerate(files, start=1):
        parent.images.create(image=strip_exif(f), position=max_pos + i)


# ---- Dashboard ---------------------------------------------------------------

@gestion_required
def dashboard(request):
    today = timezone.localdate()
    upcoming = Actualite.objects.filter(
        date_evenement__gte=today, statut=Actualite.STATUT_PUBLIE
    ).order_by("date_evenement")[:5]

    ctx = {
        "kpi_unread": Message.objects.filter(lu=False, archive=False).count(),
        "kpi_upcoming": Actualite.objects.filter(date_evenement__gte=today).count(),
        "kpi_temoignages_brouillon": Temoignage.objects.filter(statut=Temoignage.STATUT_BROUILLON).count(),
        "kpi_temoignages_publies": Temoignage.objects.filter(statut=Temoignage.STATUT_PUBLIE).count(),
        "kpi_medias": Media.objects.filter(publie=True).count(),
        "recent_messages": Message.objects.filter(archive=False)[:5],
        "upcoming_actualites": upcoming,
    }
    return render(request, "gestion/dashboard.html", ctx)


# ---- Actualités --------------------------------------------------------------

@gestion_required
def actualites_liste(request):
    page_form = ActualitesPageForm(request.POST or None, instance=ActualitesPage.get_solo())
    if request.method == "POST" and page_form.is_valid():
        page_form.save()
        messages.success(request, "En-tête de la page mis à jour.")
        target = reverse("gestion:actualites_liste")
        qs = request.GET.urlencode()
        return redirect(f"{target}?{qs}" if qs else target)

    qs = Actualite.objects.all()
    type_filter = request.GET.get("type")
    statut_filter = request.GET.get("statut")
    if type_filter:
        qs = qs.filter(type=type_filter)
    if statut_filter:
        qs = qs.filter(statut=statut_filter)
    return render(request, "gestion/actualites/list.html", {
        "actualites": qs,
        "type_filter": type_filter,
        "statut_filter": statut_filter,
        "type_choices": Actualite.TYPE_CHOICES,
        "statut_choices": Actualite.STATUT_CHOICES,
        "page_form": page_form,
    })


@gestion_required
def actualite_form(request, pk=None):
    instance = get_object_or_404(Actualite, pk=pk) if pk is not None else None
    form = ActualiteForm(request.POST or None, instance=instance)
    image_formset = (
        ActualiteImageFormSet(request.POST or None, instance=instance)
        if instance is not None else None
    )

    files, img_errors = _validate_new_images(request)
    formset_ok = image_formset is None or image_formset.is_valid()
    if (
        request.method == "POST"
        and form.is_valid() and formset_ok and not img_errors
    ):
        with transaction.atomic():
            obj = form.save()
            if image_formset is not None:
                image_formset.save()
            _save_new_images(obj, files)
        messages.success(request, f"Actualité « {obj.titre} » enregistrée.")
        return redirect("gestion:actualite_modifier", pk=obj.pk)
    if request.method == "POST":
        _flash_save_blocked(request, files)
    return render(request, "gestion/actualites/form.html", {
        "form": form,
        "image_formset": image_formset,
        "instance": instance,
        "nouvelles_errors": img_errors,
    })


@gestion_required
def actualite_supprimer(request, pk):
    obj = get_object_or_404(Actualite, pk=pk)
    if request.method == "POST":
        titre = obj.titre
        # CASCADE delete on ActualiteImage triggers pre_delete -> file cleanup.
        obj.delete()
        messages.success(request, f"Actualité « {titre} » supprimée.")
        return redirect("gestion:actualites_liste")
    return render(request, "gestion/confirm_delete.html", {
        "objet": obj,
        "label": "actualité",
        "retour_url": reverse("gestion:actualites_liste"),
    })


# ---- Carnet (billets courts) -------------------------------------------------

@gestion_required
def billets_liste(request):
    qs = Billet.objects.all()
    statut_filter = request.GET.get("statut")
    if statut_filter:
        qs = qs.filter(statut=statut_filter)
    return render(request, "gestion/carnet/list.html", {
        "billets": qs,
        "statut_filter": statut_filter,
        "statut_choices": Billet.STATUT_CHOICES,
    })


@gestion_required
def billet_form(request, pk=None):
    instance = get_object_or_404(Billet, pk=pk) if pk is not None else None
    form = BilletForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, f"Billet « {obj.titre} » enregistré.")
        return redirect("gestion:billet_modifier", pk=obj.pk)
    return render(request, "gestion/carnet/form.html", {
        "form": form,
        "instance": instance,
    })


@gestion_required
def billet_supprimer(request, pk):
    obj = get_object_or_404(Billet, pk=pk)
    if request.method == "POST":
        titre = obj.titre
        obj.delete()
        messages.success(request, f"Billet « {titre} » supprimé.")
        return redirect("gestion:billets_liste")
    return render(request, "gestion/confirm_delete.html", {
        "objet": obj,
        "label": "billet",
        "retour_url": reverse("gestion:billets_liste"),
    })


# ---- Discothèque (chansons) -------------------------------------------------

# Filtre publié : "1" = publiées, "0" = brouillons, "" = toutes.
DISCOTHEQUE_PUBLIE_FILTRES = {"1": True, "0": False}


@gestion_required
def chansons_liste(request):
    page_form = DiscothequePageForm(request.POST or None, instance=DiscothequePage.get_solo())
    if request.method == "POST" and page_form.is_valid():
        page_form.save()
        messages.success(request, "En-tête de la page mis à jour.")
        target = reverse("gestion:chansons_liste")
        qs_str = request.GET.urlencode()
        return redirect(f"{target}?{qs_str}" if qs_str else target)

    qs = Chanson.objects.all()
    publie_filter = request.GET.get("publie", "")
    if publie_filter in DISCOTHEQUE_PUBLIE_FILTRES:
        qs = qs.filter(publie=DISCOTHEQUE_PUBLIE_FILTRES[publie_filter])
    return render(request, "gestion/discotheque/list.html", {
        "chansons": qs,
        "publie_filter": publie_filter,
        "page_form": page_form,
    })


@gestion_required
def chanson_form(request, pk=None):
    instance = get_object_or_404(Chanson, pk=pk) if pk is not None else None
    form = ChansonForm(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, f"Chanson « {obj} » enregistrée.")
        return redirect("gestion:chanson_modifier", pk=obj.pk)
    return render(request, "gestion/discotheque/form.html", {
        "form": form,
        "instance": instance,
    })


@gestion_required
def chanson_supprimer(request, pk):
    obj = get_object_or_404(Chanson, pk=pk)
    if request.method == "POST":
        label = str(obj)
        # Le fichier illustration n'est pas nettoyé par CASCADE ; on le supprime explicitement.
        if obj.illustration:
            obj.illustration.delete(save=False)
        obj.delete()
        messages.success(request, f"Chanson « {label} » supprimée.")
        return redirect("gestion:chansons_liste")
    return render(request, "gestion/confirm_delete.html", {
        "objet": obj,
        "label": "chanson",
        "retour_url": reverse("gestion:chansons_liste"),
    })


# ---- Témoignages -------------------------------------------------------------

@gestion_required
def temoignages_liste(request):
    page_form = TemoignagesPageForm(request.POST or None, instance=TemoignagesPage.get_solo())
    if request.method == "POST" and page_form.is_valid():
        page_form.save()
        messages.success(request, "En-tête de la page mis à jour.")
        target = reverse("gestion:temoignages_liste")
        qs = request.GET.urlencode()
        return redirect(f"{target}?{qs}" if qs else target)

    qs = Temoignage.objects.all()
    statut_filter = request.GET.get("statut")
    if statut_filter:
        qs = qs.filter(statut=statut_filter)
    return render(request, "gestion/temoignages/list.html", {
        "temoignages": qs,
        "statut_filter": statut_filter,
        "statut_choices": Temoignage.STATUT_CHOICES,
        "page_form": page_form,
    })


@gestion_required
def temoignage_form(request, pk=None):
    instance = get_object_or_404(Temoignage, pk=pk) if pk is not None else None
    form = TemoignageForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, f"Témoignage de {obj.auteur} enregistré.")
        return redirect("gestion:temoignages_liste")
    return render(request, "gestion/temoignages/form.html", {
        "form": form,
        "instance": instance,
    })


@gestion_required
def temoignage_supprimer(request, pk):
    obj = get_object_or_404(Temoignage, pk=pk)
    if request.method == "POST":
        nom = obj.auteur
        obj.delete()
        messages.success(request, f"Témoignage de {nom} supprimé.")
        return redirect("gestion:temoignages_liste")
    return render(request, "gestion/confirm_delete.html", {
        "objet": obj,
        "label": "témoignage",
        "retour_url": reverse("gestion:temoignages_liste"),
    })


# ---- Galerie -----------------------------------------------------------------

@gestion_required
def galerie_liste(request):
    page_form = GaleriePageForm(request.POST or None, instance=GaleriePage.get_solo())
    if request.method == "POST" and page_form.is_valid():
        page_form.save()
        messages.success(request, "En-tête de la page mis à jour.")
        target = reverse("gestion:galerie_liste")
        qs_str = request.GET.urlencode()
        return redirect(f"{target}?{qs_str}" if qs_str else target)

    qs = Media.objects.all()
    categorie_filter = request.GET.get("categorie")
    if categorie_filter:
        qs = qs.filter(categorie=categorie_filter)
    return render(request, "gestion/galerie/list.html", {
        "medias": qs,
        "categorie_filter": categorie_filter,
        "categorie_choices": Media.CATEGORIE_CHOICES,
        "page_form": page_form,
    })


@gestion_required
def media_form(request, pk=None):
    instance = get_object_or_404(Media, pk=pk) if pk is not None else None
    form = MediaForm(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Média enregistré.")
        return redirect("gestion:galerie_liste")
    return render(request, "gestion/galerie/form.html", {
        "form": form,
        "instance": instance,
    })


@gestion_required
def media_supprimer(request, pk):
    obj = get_object_or_404(Media, pk=pk)
    if request.method == "POST":
        if obj.fichier:
            obj.fichier.delete(save=False)
        obj.delete()
        messages.success(request, "Média supprimé.")
        return redirect("gestion:galerie_liste")
    return render(request, "gestion/confirm_delete.html", {
        "objet": obj,
        "label": "média",
        "retour_url": reverse("gestion:galerie_liste"),
    })


# ---- Messages (inbox) --------------------------------------------------------

MESSAGES_FILTRES = {"inbox", "archives", "non-lus"}


@gestion_required
def messages_liste(request):
    show = request.GET.get("filtre", "inbox")
    if show not in MESSAGES_FILTRES:
        show = "inbox"
    qs = Message.objects.all()
    if show == "inbox":
        qs = qs.filter(archive=False)
    elif show == "archives":
        qs = qs.filter(archive=True)
    elif show == "non-lus":
        qs = qs.filter(lu=False, archive=False)
    return render(request, "gestion/messages/list.html", {
        "messages_list": qs,
        "filtre": show,
    })


@gestion_required
def message_detail(request, pk):
    msg = get_object_or_404(Message, pk=pk)
    action = request.POST.get("action") if request.method == "POST" else None
    if action == "marquer_non_lu":
        msg.lu = False
        msg.save(update_fields=["lu"])
        messages.success(request, "Message marqué comme non lu.")
        # Retour à l'inbox, sinon l'auto-mark-read ci-dessous annule le changement.
        return redirect("gestion:messages_liste")
    if action == "archiver":
        msg.archive = True
        msg.lu = True
        msg.save(update_fields=["archive", "lu"])
        messages.success(request, "Message archivé.")
        return redirect("gestion:messages_liste")
    if action == "desarchiver":
        msg.archive = False
        msg.save(update_fields=["archive"])
        return redirect("gestion:message_detail", pk=msg.pk)
    if action == "supprimer":
        msg.delete()
        messages.success(request, "Message supprimé.")
        return redirect("gestion:messages_liste")

    # Lecture d'un message : marquage auto comme lu.
    # Mute-on-GET assumé : la seule mutation possible via CSRF est de basculer
    # `lu=True` (idempotent, sans perte de donnée). Le gain UX justifie la
    # dérogation au principe « GET safe ».
    if not msg.lu:
        msg.lu = True
        msg.save(update_fields=["lu"])

    return render(request, "gestion/messages/detail.html", {"msg": msg})


# ---- Page /contact/ (singleton) ---------------------------------------------

@gestion_required
def contact_page_form(request):
    obj = ContactPage.get_solo()
    form = ContactPageForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Page /contact/ mise à jour.")
        return redirect("gestion:contact_page")
    return render(request, "gestion/contact_page/form.html", {
        "form": form,
        "instance": obj,
    })


# ---- Page d'accueil (singleton) ---------------------------------------------

@gestion_required
def accueil_form(request):
    obj = Accueil.get_solo()
    form = AccueilForm(request.POST or None, request.FILES or None, instance=obj)
    image_formset = AccueilImageFormSet(request.POST or None, instance=obj)

    files, img_errors = _validate_new_images(request)
    if (
        request.method == "POST"
        and form.is_valid() and image_formset.is_valid() and not img_errors
    ):
        with transaction.atomic():
            form.save()
            image_formset.save()
            _save_new_images(obj, files)
        messages.success(request, "Page d'accueil mise à jour.")
        return redirect("gestion:accueil")
    if request.method == "POST":
        _flash_save_blocked(request, files)
    return render(request, "gestion/accueil/form.html", {
        "form": form,
        "image_formset": image_formset,
        "instance": obj,
        "nouvelles_errors": img_errors,
    })


# ---- Personnes (Jacques Bertin, Bruno Boulais) ------------------------------

PERSONNE_LABELS = {
    Personne.ROLE_SUJET: ("Jacques Bertin", "pages:bertin", "gestion:personne_bertin"),
    Personne.ROLE_AUTEUR: ("Bruno Boulais (l'auteur)", "pages:auteur", "gestion:personne_auteur"),
}


@gestion_required
def personne_form(request, role):
    if role not in PERSONNE_LABELS:
        raise Http404
    obj, _ = Personne.objects.get_or_create(role=role, defaults={"nom": PERSONNE_LABELS[role][0]})
    form = PersonneForm(request.POST or None, request.FILES or None, instance=obj)
    image_formset = PersonneImageFormSet(request.POST or None, instance=obj)

    files, img_errors = _validate_new_images(request)
    if (
        request.method == "POST"
        and form.is_valid() and image_formset.is_valid() and not img_errors
    ):
        with transaction.atomic():
            form.save()
            image_formset.save()
            _save_new_images(obj, files)
        messages.success(request, f"« {obj.nom} » mis à jour.")
        return redirect(PERSONNE_LABELS[role][2])
    if request.method == "POST":
        _flash_save_blocked(request, files)
    label, public_url, _ = PERSONNE_LABELS[role]
    return render(request, "gestion/personnes/form.html", {
        "form": form,
        "image_formset": image_formset,
        "instance": obj,
        "label": label,
        "public_url": public_url,
        "role": role,
        "nouvelles_errors": img_errors,
    })


# ---- Livre (singleton + liens d'achat) --------------------------------------

@gestion_required
def livre_form(request):
    livre, _ = Livre.objects.get_or_create(pk=1)
    form = LivreForm(request.POST or None, request.FILES or None, instance=livre)
    formset = LienAchatFormSet(request.POST or None, instance=livre)
    image_formset = LivreImageFormSet(request.POST or None, instance=livre)

    files, img_errors = _validate_new_images(request)
    if (
        request.method == "POST"
        and form.is_valid() and formset.is_valid() and image_formset.is_valid()
        and not img_errors
    ):
        with transaction.atomic():
            form.save()
            formset.save()
            image_formset.save()
            _save_new_images(livre, files)
        messages.success(request, "Livre enregistré.")
        return redirect("gestion:livre")
    if request.method == "POST":
        _flash_save_blocked(request, files)
    return render(request, "gestion/livre/form.html", {
        "form": form,
        "formset": formset,
        "image_formset": image_formset,
        "livre": livre,
        "nouvelles_errors": img_errors,
    })


# ---- HTMX endpoints: per-row image actions (instant Supprimer) --------------

def _make_image_supprimer(image_model, parent_attr):
    """Build a `@require_POST` HTMX endpoint that deletes one image row.

    Returns an OOB swap that decrements the formset's management form counters
    (`images-TOTAL_FORMS` and `images-INITIAL_FORMS`); without it, the next
    submit fails because Django expects N forms in POST while the DOM only
    has N-1 prefixes left.
    """
    @gestion_required
    @require_POST
    def view(request, image_pk):
        img = get_object_or_404(image_model, pk=image_pk)
        parent = getattr(img, parent_attr)
        img.delete()
        new_count = parent.images.count()
        # Body holds only OOB elements: htmx extracts them by id, leaving an
        # empty body which `outerHTML`-swaps over the row target — removing it.
        html = (
            f'<input id="id_images-TOTAL_FORMS" name="images-TOTAL_FORMS" '
            f'type="hidden" value="{new_count}" hx-swap-oob="true">'
            f'<input id="id_images-INITIAL_FORMS" name="images-INITIAL_FORMS" '
            f'type="hidden" value="{new_count}" hx-swap-oob="true">'
        )
        return HttpResponse(html)
    return view


accueil_image_supprimer = _make_image_supprimer(AccueilImage, "accueil")
livre_image_supprimer = _make_image_supprimer(LivreImage, "livre")
personne_image_supprimer = _make_image_supprimer(PersonneImage, "personne")
actualite_image_supprimer = _make_image_supprimer(ActualiteImage, "actualite")


# ---- Paramètres (singleton) -------------------------------------------------

@gestion_required
def parametres_form(request):
    obj = Parametres.get_solo()
    form = ParametresForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Paramètres mis à jour.")
        return redirect("gestion:parametres")
    return render(request, "gestion/parametres/form.html", {"form": form})
