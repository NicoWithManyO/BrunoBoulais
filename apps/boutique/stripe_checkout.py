"""Création de la Session Stripe Checkout hébergée pour le paiement CB.

Checkout Session (redirection plein écran vers checkout.stripe.com) plutôt
qu'Elements : SCA/3DS gérés par Stripe et aucune modif de CSP. Le paiement
n'est jamais confirmé ici — seul le webhook (source de vérité) valide.
"""
import stripe
from django.conf import settings
from django.urls import reverse


def creer_session_checkout(commande, request):
    """Crée la Session Stripe pour une commande et renvoie l'objet session.

    Les ``line_items`` reprennent les snapshots des lignes (libellé + prix figés)
    plus une ligne « Frais de port ». ``metadata.commande_id`` permet au webhook
    de retrouver la commande à confirmer.
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY
    line_items = [
        {
            "price_data": {
                "currency": "eur",
                "product_data": {"name": ligne.libelle},
                "unit_amount": ligne.prix_unitaire_cents,
            },
            "quantity": ligne.quantite,
        }
        for ligne in commande.lignes.all()
    ]
    if commande.frais_port_cents:
        line_items.append(
            {
                "price_data": {
                    "currency": "eur",
                    "product_data": {
                        "name": f"Frais de port ({commande.get_mode_livraison_display()})"
                    },
                    "unit_amount": commande.frais_port_cents,
                },
                "quantity": 1,
            }
        )
    return stripe.checkout.Session.create(
        mode="payment",
        line_items=line_items,
        success_url=request.build_absolute_uri(reverse("boutique:paiement_success")),
        cancel_url=request.build_absolute_uri(reverse("boutique:paiement_annule")),
        customer_email=commande.email or None,
        client_reference_id=commande.reference_commande,
        metadata={"commande_id": str(commande.pk)},
    )
