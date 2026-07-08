"""Calculs de prix de la boutique — fonctions pures (testables sans session)."""

from apps.parametres.models import Parametres

from .models import Commande, TranchePort

# Colonne de prix de la tranche selon le mode de livraison choisi.
_CHAMP_PRIX = {
    Commande.LIVRAISON_POINT_RELAIS: "prix_relais_cents",
    Commande.LIVRAISON_DOMICILE: "prix_domicile_cents",
}


def montant_euros(cents):
    """Formate un montant en centimes pour l'affichage FR : 2410 → "24,10 €"."""
    return f"{cents / 100:.2f}".replace(".", ",") + " €"


def poids_total_g(lignes):
    """Poids total du chapeau (grammes) : somme des poids unitaires × quantités."""
    return sum(ligne["produit"].poids_g * ligne["quantite"] for ligne in lignes)


def tranche_applicable(lignes):
    """Tranche de port couvrant le poids total du chapeau.

    Première tranche dont le poids max ≥ poids total ; un poids qui dépasse la plus
    lourde tranche est clampé sur elle (jamais de port nul par dépassement). ``None``
    si aucune tranche n'est configurée. Résolue une fois par panier, puis lue pour
    chaque mode via ``frais_port_cents``.

    Le poids d'emballage (paramétrable) est ajouté une seule fois au panier.
    """
    poids = poids_total_g(lignes) + Parametres.get_solo().poids_emballage_g
    return TranchePort.objects.filter(poids_max_g__gte=poids).first() or TranchePort.objects.last()


def frais_port_cents(tranche, mode_livraison):
    """Prix de port (centimes) pour une tranche et un mode de livraison.

    ``None`` si le port est indéterminé — tranche absente (grille non configurée) ou
    mode inconnu/vide. Dans ce cas la commande ne doit pas être tarifée ni validée.
    """
    attr = _CHAMP_PRIX.get(mode_livraison)
    if tranche is None or attr is None:
        return None
    return getattr(tranche, attr)
