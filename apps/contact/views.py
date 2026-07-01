import logging
import math

from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.core.ratelimit import bucket_usage, log_ip_unresolved_dedup, ratelimit_bucket
from apps.core.seo import seo

from .forms import CommandeForm
from .integrale import VOLUMES_CONTENU
from .models import (
    FRAIS_PORT_CENTS,
    PRIX_OFFRE_CENTS,
    PRIX_UNITE_CENTS,
    PRODUIT_LIVRE,
    PRODUIT_VOLUMES,
    PRODUITS_AVEC_LIVRE,
    PRODUITS_OFFRE_COMPLETE,
    ContactPage,
    Message,
    montant_detail,
    quantite_articles,
)

logger = logging.getLogger(__name__)

# Rate-limit : 5 POST/heure par bucket IP (helpers partagés dans apps.core.ratelimit).
_RL_GROUP = "contact:contact"
_RL_RATE = "5/h"
_RL_LOG_KEY = "apps.contact.views:ip-unresolved-logged"


def commande(request):
    rate_limited = False
    ip_unresolved = False
    retry_after = None
    if request.method == "POST":
        form = CommandeForm(request.POST)
        # Honeypot trip = bot. On burn le bucket (pénaliser) puis on redirect
        # /merci/ pour ne pas révéler qu'on a détecté le piège (anti-fingerprint).
        if (request.POST.get("website") or "").strip():
            bucket = ratelimit_bucket(request)
            if bucket is None:
                log_ip_unresolved_dedup(request, log_key=_RL_LOG_KEY, label="Contact")
            else:
                bucket_usage(request, bucket, group=_RL_GROUP, rate=_RL_RATE, increment=True)
            # Purge d'une éventuelle commande résiduelle : le piège ne doit pas
            # réafficher le récap d'une commande précédente sur /merci/.
            request.session.pop("order_ref", None)
            return redirect(reverse("contact:merci"))
        if form.is_valid():
            bucket = ratelimit_bucket(request)
            if bucket is None:
                log_ip_unresolved_dedup(request, log_key=_RL_LOG_KEY, label="Contact")
                ip_unresolved = True
            else:
                usage = bucket_usage(request, bucket, group=_RL_GROUP, rate=_RL_RATE, increment=False)
                if usage is not None and usage["count"] >= usage["limit"]:
                    rate_limited = True
                    retry_after = max(1, math.ceil(usage["time_left"]))
                else:
                    msg = form.save_and_notify()
                    bucket_usage(request, bucket, group=_RL_GROUP, rate=_RL_RATE, increment=True)
                    # Référence conservée pour afficher le récap + la consigne de
                    # paiement sur /merci/ (mode/quantité relus depuis le Message).
                    if msg.sujet == Message.SUJET_COMMANDE and msg.mode_paiement:
                        request.session["order_ref"] = msg.pk
                    else:
                        request.session.pop("order_ref", None)
                    return redirect(reverse("contact:merci"))
    else:
        form = CommandeForm()
    response = render(
        request,
        "contact/commande.html",
        {
            "form": form,
            "page": ContactPage.get_solo(),
            "commande_value": Message.SUJET_COMMANDE,
            "produit_livre": PRODUIT_LIVRE,
            "produit_volumes": PRODUIT_VOLUMES,
            # Catégories d'offres pilotant l'affichage conditionnel côté navigateur.
            "offres_categories": {
                "avecLivre": list(PRODUITS_AVEC_LIVRE),
                "offreComplete": list(PRODUITS_OFFRE_COMPLETE),
            },
            "volumes_contenu": VOLUMES_CONTENU,
            "paiement_cheque": Message.PAIEMENT_CHEQUE,
            "paiement_virement": Message.PAIEMENT_VIREMENT,
            "livraison_domicile": Message.LIVRAISON_DOMICILE,
            "mondial_relay_brand": settings.MONDIAL_RELAY_BRAND,
            # Tarifs pour le récap calculé côté navigateur (source = centimes Python).
            "tarifs": {
                "prixUniteCents": PRIX_UNITE_CENTS,
                "prixOffreCents": PRIX_OFFRE_CENTS,
                "fraisPortCents": {
                    f"{variante}|{mode}": cents
                    for (variante, mode), cents in FRAIS_PORT_CENTS.items()
                },
            },
            "rate_limited": rate_limited,
            "ip_unresolved": ip_unresolved,
            **seo(
                request,
                title="Contact & commande · Bruno Boulais",
                description="Commander le livre ou écrire à Bruno Boulais.",
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


def commande_merci(request):
    # Référence lue une seule fois (consigne de paiement affichée au retour du
    # formulaire) : un rechargement retombe sur le simple remerciement.
    ref = request.session.pop("order_ref", None)
    order = Message.objects.filter(pk=ref).first() if ref else None
    detail = (
        montant_detail(
            order.produit,
            quantite_articles(order.produit, order.nb_exemplaires, order.volumes),
            order.mode_livraison,
        )
        if order
        else None
    )
    return render(
        request,
        "contact/commande_merci.html",
        {
            "page": ContactPage.get_solo(),
            "order": order,
            "montant": detail["total"] if detail else "",
            "paiement_cheque": Message.PAIEMENT_CHEQUE,
            "paiement_virement": Message.PAIEMENT_VIREMENT,
            **seo(request, title="Message envoyé · Bruno Boulais"),
        },
    )
