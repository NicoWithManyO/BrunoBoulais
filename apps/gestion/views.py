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

from apps.actualites.models import (
    Actualite,
    ActualiteImage,
    ActualitesPage,
)
from apps.boutique.models import BoutiquePage, Commande, Produit, TranchePort
from apps.carnet.models import Billet, BilletImageContenu
from apps.contact.models import (
    ContactPage,
    Message,
    montant_detail,
    quantite_articles,
)
from apps.core.images import strip_exif
from apps.core.templatetags.richtext import richtext_plain
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
    BilletImageContenuFormSet,
    BoutiquePageForm,
    ChansonForm,
    ContactPageForm,
    DiscothequePageForm,
    EmballageForm,
    ProduitForm,
    GaleriePageForm,
    LienAchatFormSet,
    LivreForm,
    LivreImageFormSet,
    MediaForm,
    ParametresForm,
    PersonneForm,
    PersonneImageFormSet,
    TemoignageForm,
    TranchePortForm,
    TemoignagesPageForm,
)


# ---- Helpers for multi-image upload field shared across editors -------------

def _validate_new_images(request, field_name="nouvelles_images"):
    """Validate files dropped into a multi-file upload field.

    Returns (files, errors) — caller persists the files post-parent-save.
    Errors are prefixed with the offending filename so the user knows which
    file in a multi-upload batch was rejected.
    """
    files = request.FILES.getlist(field_name) if request.method == "POST" else []
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


def _save_new_images(parent, files, relation="images"):
    """Create one image row per file at the next available `position`.

    `relation` is the reverse manager name (e.g. "images" for the carousel,
    "images_contenu" for in-body images).
    """
    if not files:
        return
    manager = getattr(parent, relation)
    max_pos = manager.aggregate(Max("position"))["position__max"] or 0
    for i, f in enumerate(files, start=1):
        manager.create(image=strip_exif(f), position=max_pos + i)


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
        and form.is_valid() and formset_ok
        and not img_errors
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
    contenu_formset = (
        BilletImageContenuFormSet(request.POST or None, instance=instance)
        if instance is not None else None
    )

    files_contenu, img_contenu_errors = _validate_new_images(request, "nouvelles_images_contenu")
    contenu_ok = contenu_formset is None or contenu_formset.is_valid()
    if (
        request.method == "POST"
        and form.is_valid() and contenu_ok
        and not img_contenu_errors
    ):
        with transaction.atomic():
            obj = form.save()
            if contenu_formset is not None:
                contenu_formset.save()
            _save_new_images(obj, files_contenu, relation="images_contenu")
        messages.success(request, f"Billet « {obj.titre} » enregistré.")
        return redirect("gestion:billet_modifier", pk=obj.pk)
    if request.method == "POST":
        _flash_save_blocked(request, files_contenu)
    return render(request, "gestion/carnet/form.html", {
        "form": form,
        "contenu_formset": contenu_formset,
        "instance": instance,
        "nouvelles_contenu_errors": img_contenu_errors,
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


@gestion_required
@require_POST
def billet_image_contenu_ajouter(request, pk=None):
    """Upload immédiat (HTMX) d'images de contenu : enregistre le billet sans
    passer par le bouton « Créer » (en brouillon par défaut), attache les
    fichiers, puis recharge la page d'édition où les repères [image:N]
    deviennent visibles. `contenu` non requis ici : on doit pouvoir uploader
    les images AVANT de rédiger le texte qui les référence."""
    instance = get_object_or_404(Billet, pk=pk) if pk is not None else None
    form = BilletForm(request.POST, instance=instance)
    form.fields["contenu"].required = False
    files, file_errors = _validate_new_images(request, "nouvelles_images_contenu")
    if not files and not file_errors:
        file_errors = ["Sélectionnez au moins une image à uploader."]
    if form.is_valid() and not file_errors:
        with transaction.atomic():
            billet = form.save()
            _save_new_images(billet, files, relation="images_contenu")
        messages.success(request, f"{len(files)} image(s) ajoutée(s).")
        resp = HttpResponse(status=204)
        resp["HX-Redirect"] = reverse("gestion:billet_modifier", args=[billet.pk])
        return resp
    errors = list(file_errors)
    if "titre" in form.errors:
        errors.append("Renseignez un titre avant d'ajouter une image.")
    errors += list(form.errors.get("date_publication", []))
    return render(request, "gestion/_images_contenu_errors.html", {"errors": errors})


@gestion_required
@require_POST
def billet_annuler(request, pk):
    """« Annuler » sur l'édition d'un billet. Supprime les brouillons restés
    vides (créés à la volée par l'upload d'image puis abandonnés) — sinon simple
    retour à la liste. La suppression cascade sur les images (fichiers nettoyés
    via pre_delete)."""
    billet = get_object_or_404(Billet, pk=pk)
    if billet.statut == Billet.STATUT_BROUILLON and not richtext_plain(billet.contenu).strip():
        billet.delete()
        messages.info(request, f"Billet vide « {billet.titre} » abandonné et supprimé.")
    resp = HttpResponse(status=204)
    resp["HX-Redirect"] = reverse("gestion:billets_liste")
    return resp


@gestion_required
@require_POST
def billet_preview(request, pk=None):
    """Rend (HTMX) le feuillet du Carnet tel qu'il apparaîtra sur le site, à
    partir des valeurs courantes du formulaire d'édition — sans rien enregistrer.
    Tolérant : une saisie partielle ou invalide donne un aperçu partiel, jamais
    une erreur. Les repères [image:N] référencent les images du billet, avec leurs
    largeur/alignement/ordre courants du formset (même non encore enregistrés)."""
    instance = get_object_or_404(Billet, pk=pk) if pk is not None else None
    form = BilletForm(request.POST, instance=instance)
    for name in ("titre", "contenu", "date_publication"):
        form.fields[name].required = False
    if form.is_valid():
        billet = form.save(commit=False)
    else:
        billet = instance or Billet()
        billet.titre = request.POST.get("titre", billet.titre)
        billet.contenu = request.POST.get("contenu", billet.contenu)
    if not billet.date_publication:
        billet.date_publication = getattr(instance, "date_publication", None) or timezone.now()
    images = _preview_content_images(request, instance)
    return render(request, "gestion/_billet_preview.html", {"billet": billet, "images": images})


def _preview_content_images(request, instance):
    """Images de contenu à afficher dans l'aperçu, avec les largeur/alignement/
    ordre courants du formset POSTé (appliqués en mémoire, sans sauvegarde).
    Replie sur l'état en base si le formset est absent ou illisible."""
    if instance is None:
        return []
    try:
        formset = BilletImageContenuFormSet(request.POST, instance=instance)
        formset.is_valid()  # peuple form.instance via _post_clean ; résultat ignoré (mode tolérant)
        applied = [
            f.instance for f in formset.forms
            if f.instance.pk and not getattr(f, "cleaned_data", {}).get("DELETE")
        ]
    except Exception:
        return instance.images_contenu.all()
    if not applied:
        return instance.images_contenu.all()
    applied.sort(key=lambda img: img.position)
    return applied


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
    type_filter = request.GET.get("type", "")
    if type_filter in dict(Chanson.TYPE_CHOICES):
        qs = qs.filter(type=type_filter)
    return render(request, "gestion/discotheque/list.html", {
        "chansons": qs,
        "publie_filter": publie_filter,
        "type_filter": type_filter,
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
        # Les fichiers (illustration, audio) ne sont pas nettoyés par CASCADE ;
        # on les supprime explicitement.
        if obj.illustration:
            obj.illustration.delete(save=False)
        if obj.audio:
            obj.audio.delete(save=False)
        obj.delete()
        messages.success(request, f"Chanson « {label} » supprimée.")
        return redirect("gestion:chansons_liste")
    return render(request, "gestion/confirm_delete.html", {
        "objet": obj,
        "label": "chanson",
        "retour_url": reverse("gestion:chansons_liste"),
    })


# ---- Boutique (produits) ----------------------------------------------------

# Filtre publié : "1" = publiés, "0" = brouillons, "" = tous.
BOUTIQUE_PUBLIE_FILTRES = {"1": True, "0": False}


@gestion_required
def produits_liste(request):
    page_form = BoutiquePageForm(request.POST or None, instance=BoutiquePage.get_solo())
    if request.method == "POST" and page_form.is_valid():
        page_form.save()
        messages.success(request, "En-tête de la page mis à jour.")
        target = reverse("gestion:produits_liste")
        qs_str = request.GET.urlencode()
        return redirect(f"{target}?{qs_str}" if qs_str else target)

    qs = Produit.objects.all()
    publie_filter = request.GET.get("publie", "")
    if publie_filter in BOUTIQUE_PUBLIE_FILTRES:
        qs = qs.filter(publie=BOUTIQUE_PUBLIE_FILTRES[publie_filter])
    return render(request, "gestion/boutique/list.html", {
        "produits": qs,
        "publie_filter": publie_filter,
        "page_form": page_form,
    })


@gestion_required
def produit_form(request, pk=None):
    instance = get_object_or_404(Produit, pk=pk) if pk is not None else None
    form = ProduitForm(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, f"Produit « {obj} » enregistré.")
        return redirect("gestion:produit_modifier", pk=obj.pk)
    return render(request, "gestion/boutique/form.html", {
        "form": form,
        "instance": instance,
    })


@gestion_required
def produit_supprimer(request, pk):
    obj = get_object_or_404(Produit, pk=pk)
    if request.method == "POST":
        label = str(obj)
        # Le fichier illustration n'est pas nettoyé par CASCADE : on le supprime
        # explicitement.
        if obj.illustration:
            obj.illustration.delete(save=False)
        obj.delete()
        messages.success(request, f"Produit « {label} » supprimé.")
        return redirect("gestion:produits_liste")
    return render(request, "gestion/confirm_delete.html", {
        "objet": obj,
        "label": "produit",
        "retour_url": reverse("gestion:produits_liste"),
    })


@gestion_required
def tranches_port_liste(request):
    # Poids d'emballage : configuré ici (page port) plutôt que dans les paramètres.
    emballage_form = EmballageForm(request.POST or None, instance=Parametres.get_solo())
    if request.method == "POST" and emballage_form.is_valid():
        emballage_form.save()
        messages.success(request, "Poids d'emballage enregistré.")
        return redirect("gestion:tranches_port_liste")
    return render(request, "gestion/frais_port/list.html", {
        "tranches": TranchePort.objects.all(),
        "emballage_form": emballage_form,
    })


@gestion_required
def tranche_port_form(request, pk=None):
    instance = get_object_or_404(TranchePort, pk=pk) if pk is not None else None
    form = TranchePortForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, f"Tranche « {obj} » enregistrée.")
        return redirect("gestion:tranche_port_modifier", pk=obj.pk)
    return render(request, "gestion/frais_port/form.html", {
        "form": form,
        "instance": instance,
    })


@gestion_required
def tranche_port_supprimer(request, pk):
    obj = get_object_or_404(TranchePort, pk=pk)
    if request.method == "POST":
        label = str(obj)
        obj.delete()
        messages.success(request, f"Tranche « {label} » supprimée.")
        return redirect("gestion:tranches_port_liste")
    return render(request, "gestion/confirm_delete.html", {
        "objet": obj,
        "label": "tranche de frais de port",
        "retour_url": reverse("gestion:tranches_port_liste"),
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
        "commande_value": Message.SUJET_COMMANDE,
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

    # Détail chiffré d'une commande (articles + port + total), formaté côté vue
    # pour garder le template sans logique. None hors commande / tarif inconnu.
    commande_montant = None
    if msg.sujet == Message.SUJET_COMMANDE and msg.produit:
        # None si prix inconnu ; port="à confirmer" si combinaison non tarifée.
        quantite = quantite_articles(msg.produit, msg.nb_exemplaires, msg.volumes)
        commande_montant = montant_detail(msg.produit, quantite, msg.mode_livraison)

    return render(request, "gestion/messages/detail.html", {
        "msg": msg,
        "commande_montant": commande_montant,
        "commande_value": Message.SUJET_COMMANDE,
        "livraison_domicile": Message.LIVRAISON_DOMICILE,
    })


# ---- Commandes (boutique) ----------------------------------------------------

COMMANDES_FILTRES = {"a-traiter", "payees", "archives"}


@gestion_required
def commandes_liste(request):
    show = request.GET.get("filtre", "a-traiter")
    if show not in COMMANDES_FILTRES:
        show = "a-traiter"
    qs = Commande.objects.all()
    if show == "a-traiter":
        qs = qs.filter(archive=False).exclude(statut=Commande.STATUT_PAYE)
    elif show == "payees":
        qs = qs.filter(archive=False, statut=Commande.STATUT_PAYE)
    elif show == "archives":
        qs = qs.filter(archive=True)
    return render(request, "gestion/commandes/list.html", {
        "commandes_list": qs,
        "filtre": show,
    })


@gestion_required
def commande_detail(request, pk):
    commande = get_object_or_404(Commande, pk=pk)
    action = request.POST.get("action") if request.method == "POST" else None
    if action == "marquer_paye":
        commande.statut = Commande.STATUT_PAYE
        commande.lu = True
        commande.save(update_fields=["statut", "lu"])
        messages.success(request, "Commande marquée comme payée.")
        return redirect("gestion:commande_detail", pk=commande.pk)
    if action == "marquer_non_lu":
        commande.lu = False
        commande.save(update_fields=["lu"])
        messages.success(request, "Commande marquée comme non lue.")
        # Retour à la liste, sinon l'auto-mark-read ci-dessous annule le changement.
        return redirect("gestion:commandes_liste")
    if action == "archiver":
        commande.archive = True
        commande.lu = True
        commande.save(update_fields=["archive", "lu"])
        messages.success(request, "Commande archivée.")
        return redirect("gestion:commandes_liste")
    if action == "desarchiver":
        commande.archive = False
        commande.save(update_fields=["archive"])
        return redirect("gestion:commande_detail", pk=commande.pk)
    if action == "supprimer":
        commande.delete()
        messages.success(request, "Commande supprimée.")
        return redirect("gestion:commandes_liste")

    # Lecture d'une commande : marquage auto comme lue (mute-on-GET assumé, même
    # dérogation idempotente que message_detail).
    if not commande.lu:
        commande.lu = True
        commande.save(update_fields=["lu"])

    return render(request, "gestion/commandes/detail.html", {
        "commande": commande,
        "livraison_domicile": Commande.LIVRAISON_DOMICILE,
    })


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

def _make_image_supprimer(image_model, parent_attr, relation="images"):
    """Build a `@require_POST` HTMX endpoint that deletes one image row.

    Returns an OOB swap that decrements the formset's management form counters
    (`<relation>-TOTAL_FORMS` and `<relation>-INITIAL_FORMS`); without it, the
    next submit fails because Django expects N forms in POST while the DOM only
    has N-1 prefixes left. `relation` is both the reverse manager name and the
    inline formset prefix (they match: the prefix defaults to the accessor name).
    """
    @gestion_required
    @require_POST
    def view(request, image_pk):
        img = get_object_or_404(image_model, pk=image_pk)
        parent = getattr(img, parent_attr)
        img.delete()
        new_count = getattr(parent, relation).count()
        # Body holds only OOB elements: htmx extracts them by id, leaving an
        # empty body which `outerHTML`-swaps over the row target — removing it.
        html = (
            f'<input id="id_{relation}-TOTAL_FORMS" name="{relation}-TOTAL_FORMS" '
            f'type="hidden" value="{new_count}" hx-swap-oob="true">'
            f'<input id="id_{relation}-INITIAL_FORMS" name="{relation}-INITIAL_FORMS" '
            f'type="hidden" value="{new_count}" hx-swap-oob="true">'
        )
        return HttpResponse(html)
    return view


accueil_image_supprimer = _make_image_supprimer(AccueilImage, "accueil")
livre_image_supprimer = _make_image_supprimer(LivreImage, "livre")
personne_image_supprimer = _make_image_supprimer(PersonneImage, "personne")
actualite_image_supprimer = _make_image_supprimer(ActualiteImage, "actualite")
billet_image_contenu_supprimer = _make_image_supprimer(
    BilletImageContenu, "billet", "images_contenu"
)


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
