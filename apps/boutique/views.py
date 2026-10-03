import math

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.core.ratelimit import bucket_usage, log_ip_unresolved_dedup, ratelimit_bucket
from apps.core.seo import seo

from .cart import Chapeau
from .forms import CommandeForm
from .models import BoutiquePage, Commande, LigneCommande, Produit
from .pricing import frais_port_cents, montant_euros, tranche_applicable

# Rate-limit : 5 POST/heure par bucket IP (helpers partagés dans apps.core.ratelimit).
_RL_GROUP = "boutique:commande"
_RL_RATE = "5/h"
_RL_LOG_KEY = "apps.boutique.views:ip-unresolved-logged"


def liste(request):
    produits = Produit.objects.filter(publie=True)
    return render(
        request,
        "boutique/liste.html",
        {
            "produits": produits,
            "page": BoutiquePage.get_solo(),
            **seo(
                request,
                title="Boutique · Bruno Boulais",
                description=(
                    "Commander le livre « Jacques Bertin, le géant discret de la"
                    " chanson », l'intégrale CD et les volumes."
                ),
            ),
        },
    )


@require_POST
def chapeau_ajouter(request, pk):
    produit = get_object_or_404(Produit, pk=pk, publie=True)
    Chapeau(request).add(produit)
    messages.success(request, f"« {produit.nom} » ajouté à votre chapeau.")
    # On reste sur la page d'origine (le bandeau reflète le chapeau) ; repli sur
    # la boutique si le referer est absent ou pointe hors du site.
    dest = request.META.get("HTTP_REFERER", "")
    if not url_has_allowed_host_and_scheme(dest, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        dest = reverse("boutique:liste")
    return redirect(dest)


@require_POST
def chapeau_modifier(request, pk):
    qte = request.POST.get("quantite", "")
    chapeau = Chapeau(request)
    # Quantité invalide (non numérique) → on retire la ligne (KISS, pas d'erreur).
    chapeau.set_quantite(pk, int(qte) if qte.isdigit() else 0)
    return redirect("boutique:chapeau")


@require_POST
def chapeau_retirer(request, pk):
    Chapeau(request).remove(pk)
    return redirect("boutique:chapeau")


@require_POST
def chapeau_vider(request):
    Chapeau(request).clear()
    return redirect("boutique:chapeau")


def chapeau_voir(request):
    chapeau = Chapeau(request)
    lignes = chapeau.lignes
    # Estimation du port : tranche du poids du chapeau, port pour chaque mode.
    # ``None`` (grille non configurée) → l'affichage retombe sur « à l'étape suivante ».
    tranche = tranche_applicable(lignes) if lignes else None
    return render(
        request,
        "boutique/chapeau.html",
        {
            "lignes": lignes,
            "montant_articles": montant_euros(chapeau.montant_articles_cents),
            "frais_port": {
                Commande.LIVRAISON_POINT_RELAIS: frais_port_cents(tranche, Commande.LIVRAISON_POINT_RELAIS),
                Commande.LIVRAISON_DOMICILE: frais_port_cents(tranche, Commande.LIVRAISON_DOMICILE),
            },
            **seo(request, title="Mon chapeau · Bruno Boulais"),
        },
    )


def _creer_commande(form, chapeau, port):
    """Persiste la Commande + ses lignes avec snapshots prix/libellé du chapeau.

    ``port`` (centimes) est résolu et validé non-nul par l'appelant.
    """
    commande = form.save(commit=False)
    # Une seule hydratation du chapeau, réutilisée pour le montant des articles et les lignes.
    lignes = chapeau.lignes
    articles = sum(ligne["sous_total_cents"] for ligne in lignes)
    commande.montant_articles_cents = articles
    commande.frais_port_cents = port
    commande.montant_total_cents = articles + port
    # Bruno encaisse le chèque/virement à la main puis marque payé en gestion.
    commande.statut = Commande.STATUT_EN_ATTENTE_REGLEMENT
    commande.save()
    LigneCommande.objects.bulk_create(
        [
            LigneCommande(
                commande=commande,
                produit=ligne["produit"],
                libelle=ligne["produit"].nom,
                prix_unitaire_cents=ligne["produit"].prix_cents,
                quantite=ligne["quantite"],
            )
            for ligne in lignes
        ]
    )
    return commande


def commande(request):
    chapeau = Chapeau(request)
    lignes = chapeau.lignes
    # Pas de commande d'un chapeau vide.
    if not lignes:
        return redirect("boutique:chapeau")
    # Tranche de port résolue une fois pour le panier, relue par mode au rendu et à la création.
    tranche = tranche_applicable(lignes)
    dedicacable = any(ligne["produit"].dedicacable for ligne in lignes)
    rate_limited = False
    ip_unresolved = False
    retry_after = None
    if request.method == "POST":
        form = CommandeForm(request.POST, dedicacable=dedicacable)
        # Honeypot trip = bot. On burn le bucket puis redirect /merci/ sans rien
        # révéler (anti-fingerprint), en purgeant une éventuelle réf résiduelle.
        if (request.POST.get("website") or "").strip():
            bucket = ratelimit_bucket(request)
            if bucket is None:
                log_ip_unresolved_dedup(request, log_key=_RL_LOG_KEY, label="Boutique")
            else:
                bucket_usage(request, bucket, group=_RL_GROUP, rate=_RL_RATE, increment=True)
            request.session.pop("commande_ref", None)
            return redirect("boutique:merci")
        if form.is_valid():
            bucket = ratelimit_bucket(request)
            if bucket is None:
                log_ip_unresolved_dedup(request, log_key=_RL_LOG_KEY, label="Boutique")
                ip_unresolved = True
            else:
                usage = bucket_usage(request, bucket, group=_RL_GROUP, rate=_RL_RATE, increment=False)
                if usage is not None and usage["count"] >= usage["limit"]:
                    rate_limited = True
                    retry_after = max(1, math.ceil(usage["time_left"]))
                elif frais_port_cents(tranche, form.cleaned_data["mode_livraison"]) is None:
                    # Grille de tranches non configurée : port indéterminé. On refuse
                    # plutôt que d'enregistrer une commande à port nul.
                    form.add_error(None, "La livraison est momentanément indisponible. Merci de réessayer plus tard.")
                else:
                    port = frais_port_cents(tranche, form.cleaned_data["mode_livraison"])
                    obj = _creer_commande(form, chapeau, port)
                    bucket_usage(request, bucket, group=_RL_GROUP, rate=_RL_RATE, increment=True)
                    obj.notify()
                    chapeau.clear()
                    request.session["commande_ref"] = obj.pk
                    return redirect("boutique:merci")
    else:
        form = CommandeForm(dedicacable=dedicacable)
    response = render(
        request,
        "boutique/commande.html",
        {
            "form": form,
            "lignes": lignes,
            "dedicacable": dedicacable,
            "montant_articles": montant_euros(chapeau.montant_articles_cents),
            "montant_articles_cents": chapeau.montant_articles_cents,
            "frais_port": {
                Commande.LIVRAISON_POINT_RELAIS: frais_port_cents(tranche, Commande.LIVRAISON_POINT_RELAIS),
                Commande.LIVRAISON_DOMICILE: frais_port_cents(tranche, Commande.LIVRAISON_DOMICILE),
            },
            "livraison_point_relais": Commande.LIVRAISON_POINT_RELAIS,
            "livraison_domicile": Commande.LIVRAISON_DOMICILE,
            "paiement_cheque": Commande.PAIEMENT_CHEQUE,
            "paiement_virement": Commande.PAIEMENT_VIREMENT,
            "mondial_relay_brand": settings.MONDIAL_RELAY_BRAND,
            "rate_limited": rate_limited,
            "ip_unresolved": ip_unresolved,
            **seo(
                request,
                title="Valider ma commande · Bruno Boulais",
                description="Finaliser la commande des articles déposés dans votre chapeau.",
            ),
        },
    )
    if ip_unresolved:
        response.status_code = 503
        response["Cache-Control"] = "no-store"
    elif rate_limited:
        response.status_code = 429
        response["Retry-After"] = str(retry_after)
        response["Cache-Control"] = "no-store"
    return response


def merci(request):
    # Référence lue une seule fois : un rechargement retombe sur le simple
    # remerciement, sans le récap de paiement.
    ref = request.session.pop("commande_ref", None)
    obj = Commande.objects.filter(pk=ref).first() if ref else None
    return render(
        request,
        "boutique/merci.html",
        {
            "commande": obj,
            "paiement_cheque": Commande.PAIEMENT_CHEQUE,
            "paiement_virement": Commande.PAIEMENT_VIREMENT,
            **seo(request, title="Commande enregistrée · Bruno Boulais"),
        },
    )
