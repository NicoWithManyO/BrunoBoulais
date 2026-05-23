"""Custom backoffice for Bruno — replaces Django admin with a softer UX."""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone


def gestion_required(view_func):
    """Require an authenticated staff user; redirect to /gestion/connexion/ otherwise.

    Pure `@gestion_required` is unsafe here because allauth signup at /accounts/signup/
    is open — anyone could self-register. We gate on `is_staff` so only users
    explicitly elevated by a superuser can reach the backoffice.
    """
    check = user_passes_test(
        lambda u: u.is_authenticated and u.is_staff,
        login_url="/gestion/connexion/",
    )

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        return check(view_func)(request, *args, **kwargs)

    return wrapped

from apps.actualites.models import Actualite
from apps.contact.models import Message
from apps.galerie.models import Media
from apps.livre.models import Livre
from apps.pages.models import Page
from apps.parametres.models import Parametres
from apps.temoignages.models import Temoignage

from .forms import (
    ActualiteForm,
    LienAchatFormSet,
    LivreForm,
    MediaForm,
    ParametresForm,
    TemoignageForm,
)


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
    })


@gestion_required
def actualite_form(request, pk=None):
    instance = get_object_or_404(Actualite, pk=pk) if pk is not None else None
    form = ActualiteForm(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, f"Actualité « {obj.titre} » enregistrée.")
        return redirect("gestion:actualites_liste")
    return render(request, "gestion/actualites/form.html", {
        "form": form,
        "instance": instance,
    })


@gestion_required
def actualite_supprimer(request, pk):
    obj = get_object_or_404(Actualite, pk=pk)
    if request.method == "POST":
        titre = obj.titre
        if obj.image:
            obj.image.delete(save=False)
        obj.delete()
        messages.success(request, f"Actualité « {titre} » supprimée.")
        return redirect("gestion:actualites_liste")
    return render(request, "gestion/confirm_delete.html", {
        "objet": obj,
        "label": "actualité",
        "retour_url": reverse("gestion:actualites_liste"),
    })


# ---- Témoignages -------------------------------------------------------------

@gestion_required
def temoignages_liste(request):
    qs = Temoignage.objects.all()
    statut_filter = request.GET.get("statut")
    if statut_filter:
        qs = qs.filter(statut=statut_filter)
    return render(request, "gestion/temoignages/list.html", {
        "temoignages": qs,
        "statut_filter": statut_filter,
        "statut_choices": Temoignage.STATUT_CHOICES,
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
    qs = Media.objects.all()
    categorie_filter = request.GET.get("categorie")
    if categorie_filter:
        qs = qs.filter(categorie=categorie_filter)
    return render(request, "gestion/galerie/list.html", {
        "medias": qs,
        "categorie_filter": categorie_filter,
        "categorie_choices": Media.CATEGORIE_CHOICES,
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
    if not msg.lu:
        msg.lu = True
        msg.save(update_fields=["lu"])

    return render(request, "gestion/messages/detail.html", {"msg": msg})


# ---- Pages (stub — vraie édition par blocs = étape 6) -----------------------

@gestion_required
def pages_liste(request):
    return render(request, "gestion/pages/list.html", {
        "pages": Page.objects.all(),
    })


@gestion_required
def page_editer(request, slug):
    page = get_object_or_404(Page, slug=slug)
    return render(request, "gestion/pages/editer.html", {"page": page})


# ---- Livre (singleton + liens d'achat) --------------------------------------

@gestion_required
def livre_form(request):
    livre, _ = Livre.objects.get_or_create(pk=1)
    form = LivreForm(request.POST or None, request.FILES or None, instance=livre)
    formset = LienAchatFormSet(request.POST or None, instance=livre)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        form.save()
        formset.save()
        messages.success(request, "Livre enregistré.")
        return redirect("gestion:livre")
    return render(request, "gestion/livre/form.html", {
        "form": form,
        "formset": formset,
        "livre": livre,
    })


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
