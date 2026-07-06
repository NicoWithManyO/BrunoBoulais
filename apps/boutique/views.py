import logging
import math

import stripe
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.ratelimit import bucket_usage, log_ip_unresolved_dedup, ratelimit_bucket
from apps.core.seo import seo

from .cart import Chapeau
from .forms import CommandeForm
from .models import BoutiquePage, Commande, LigneCommande, Produit
from .pricing import frais_port_cents, montant_euros, tranche_applicable
from .stripe_checkout import creer_session_checkout

logger = logging.getLogger(__name__)

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
    return redirect("boutique:chapeau")


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
    return render(
        request,
        "boutique/chapeau.html",
        {
            "lignes": lignes,
            "montant_articles": montant_euros(chapeau.montant_articles_cents),
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
    if commande.mode_paiement == Commande.PAIEMENT_CB:
        # CB : le webhook Stripe passera la commande à « payé » (source de vérité).
        commande.statut = Commande.STATUT_EN_ATTENTE_PAIEMENT
    else:
        # Chèque/virement : Bruno encaisse à la main puis marque payé en gestion.
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
                    # plutôt que de facturer un port nul (article seul en CB).
                    form.add_error(None, "La livraison est momentanément indisponible. Merci de réessayer plus tard.")
                else:
                    port = frais_port_cents(tranche, form.cleaned_data["mode_livraison"])
                    obj = _creer_commande(form, chapeau, port)
                    bucket_usage(request, bucket, group=_RL_GROUP, rate=_RL_RATE, increment=True)
                    if obj.mode_paiement == Commande.PAIEMENT_CB:
                        # CB : on part vers Stripe. Ni notif ni vidage du chapeau
                        # ici — le webhook confirmera, le retour success videra.
                        # On lie la réf à la session navigateur : paiement_cb
                        # n'acceptera que cette commande (anti-énumération), et
                        # l'écran d'annulation pourra proposer un réessai.
                        request.session["commande_ref"] = obj.pk
                        return redirect("boutique:paiement_cb", pk=obj.pk)
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
            "paiement_cb": Commande.PAIEMENT_CB,
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


def _commande_depuis_ref(request, *, consume):
    """Charge la commande liée à la session (clé ``commande_ref``).

    ``consume=True`` retire la réf (page terminale : un rechargement retombe sur
    le simple remerciement) ; ``consume=False`` la laisse (l'annulation permet un
    réessai sur la même commande).
    """
    if consume:
        ref = request.session.pop("commande_ref", None)
    else:
        ref = request.session.get("commande_ref")
    return Commande.objects.filter(pk=ref).first() if ref else None


def merci(request):
    # Référence lue une seule fois : un rechargement retombe sur le simple
    # remerciement, sans le récap de paiement.
    obj = _commande_depuis_ref(request, consume=True)
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


def paiement_cb(request, pk):
    """Crée la Session Stripe et redirige (303) vers checkout.stripe.com.

    La commande doit être celle liée à la session navigateur (posée au checkout) :
    toute autre réf est refusée pour empêcher l'énumération des commandes d'autrui.
    Vue rejouable : après annulation, le lien « réessayer » y revient et crée
    une nouvelle session pour la même commande, sans doublon en base.
    """
    if pk != request.session.get("commande_ref"):
        return redirect("boutique:chapeau")
    commande = get_object_or_404(Commande, pk=pk)
    # commande_ref est partagée avec le flux chèque/virement : on n'ouvre Stripe
    # que pour une commande réellement en mode CB (pas de mélange de canaux).
    if commande.mode_paiement != Commande.PAIEMENT_CB:
        return redirect("boutique:chapeau")
    if commande.paye:
        return redirect("boutique:merci")
    try:
        session = creer_session_checkout(commande, request)
    except Exception:
        logger.exception(
            "Boutique: échec de création de la session Stripe pour la commande %s.",
            commande.reference_commande,
        )
        return redirect("boutique:paiement_annule")
    commande.stripe_session_id = session.id
    commande.save(update_fields=["stripe_session_id"])
    # 303 : la commande a été soumise en POST, la redirection GET vers Stripe
    # est bien une autre ressource (recommandation Stripe pour Checkout).
    return HttpResponseRedirect(session.url, status=303)


def paiement_success(request):
    # Retour Stripe. On ne vide le chapeau et n'affiche la commande que si Stripe
    # confirme le paiement de la session ({CHECKOUT_SESSION_ID} renvoyé dans
    # l'URL) : un simple GET (prefetch, favori, lien croisé) ne doit rien valider
    # ni effacer. La confirmation définitive reste le webhook.
    commande = None
    session_id = request.GET.get("session_id", "")
    if session_id:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except Exception:
            logger.warning(
                "Boutique: échec de récupération de la session Stripe %s au retour success.",
                session_id,
                exc_info=True,
            )
            session = None
        if session and session.get("payment_status") == "paid":
            commande_id = (session.get("metadata") or {}).get("commande_id")
            candidate = Commande.objects.filter(pk=commande_id).first()
            # Lien à la session navigateur : on n'affiche/ne vide que si la session
            # Stripe correspond à la commande de CE visiteur. Un session_id d'autrui
            # (URL partagée/devinée) ne doit rien révéler ni vider son chapeau.
            if candidate and candidate.pk == request.session.get("commande_ref"):
                commande = candidate
                Chapeau(request).clear()
                request.session.pop("commande_ref", None)
    return render(
        request,
        "boutique/paiement_success.html",
        {
            "commande": commande,
            **seo(request, title="Paiement reçu · Bruno Boulais"),
        },
    )


def paiement_annule(request):
    # Retour Stripe sans paiement (annulation ou échec technique). Chapeau
    # conservé ; on propose de réessayer la CB sur la même commande.
    commande = _commande_depuis_ref(request, consume=False)
    # Une réf résiduelle déjà réglée (autre flux, rejeu) ne doit rien afficher :
    # le réessai ne concerne qu'une commande encore à payer.
    if commande and commande.paye:
        commande = None
    return render(
        request,
        "boutique/paiement_annule.html",
        {
            "commande": commande,
            **seo(request, title="Paiement non abouti · Bruno Boulais"),
        },
    )


@csrf_exempt
@require_POST
def webhook_stripe(request):
    """Source de vérité du paiement CB. Vérifie la signature puis, sur
    ``checkout.session.completed`` payé, passe la commande à « payé » et notifie
    Bruno. Idempotent : un rejeu ne re-notifie pas une commande déjà payée.
    """
    try:
        event = stripe.Webhook.construct_event(
            request.body,
            request.META.get("HTTP_STRIPE_SIGNATURE", ""),
            settings.STRIPE_WEBHOOK_SECRET,
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        if session.get("payment_status") == "paid":
            commande_id = (session.get("metadata") or {}).get("commande_id")
            # Bascule atomique, restreinte à une CB en attente : parmi des rejeux
            # (éventuellement concurrents) une seule requête voit ``updated == 1``
            # et notifie. Cibler ce seul statut évite de ressusciter une commande
            # annulée/remboursée qu'un webhook tardif viendrait repasser à « payé ».
            updated = Commande.objects.filter(
                pk=commande_id, statut=Commande.STATUT_EN_ATTENTE_PAIEMENT
            ).update(statut=Commande.STATUT_PAYE)
            if updated:
                commande = Commande.objects.filter(pk=commande_id).first()
                if commande:
                    commande.notify()
            elif not Commande.objects.filter(pk=commande_id).exists():
                # Paiement confirmé mais aucune commande à honorer (metadata
                # absente/erronée) : la CB a été débitée, il faut agir à la main.
                # (updated == 0 sur une commande déjà payée = simple rejeu, silencieux.)
                logger.error(
                    "Boutique: webhook Stripe — paiement confirmé mais commande %s "
                    "introuvable ; CB débitée sans commande à honorer.",
                    commande_id,
                )
    return HttpResponse(status=200)
