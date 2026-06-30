"""Calculs de prix de la boutique — fonctions pures (testables sans session)."""

from .models import Commande

# Frais de port forfaitaires par mode de livraison (centimes). On reprend les
# montants historiques de l'ancienne commande (livre 1 ex.) appliqués au panier,
# sans calcul au poids. Faciles à ajuster ici si Bruno change de grille.
FRAIS_PORT_CENTS = {
    Commande.LIVRAISON_POINT_RELAIS: 415,
    Commande.LIVRAISON_DOMICILE: 749,
}


def montant_euros(cents):
    """Formate un montant en centimes pour l'affichage FR : 2410 → "24,10 €"."""
    return f"{cents / 100:.2f}".replace(".", ",") + " €"


def frais_port_cents(mode_livraison):
    """Forfait de port pour le mode choisi, ou None si le mode est inconnu/vide."""
    return FRAIS_PORT_CENTS.get(mode_livraison)


def total_cents(articles_cents, mode_livraison):
    """Total commande = articles + port. None si le port est indéterminé."""
    port = frais_port_cents(mode_livraison)
    if port is None:
        return None
    return articles_cents + port
