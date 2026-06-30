"""Le « chapeau » : panier de la boutique, stocké en session.

Clin d'œil à la quête au chapeau d'un spectacle. La session ne garde que
`{produit_id: quantite}` (JSON → clés string) ; les produits sont hydratés
depuis la base à la lecture, ce qui auto-nettoie les produits dépubliés/supprimés.
"""

from .models import Produit

SESSION_KEY = "chapeau"


class Chapeau:
    def __init__(self, request):
        self.session = request.session
        self.items = self.session.setdefault(SESSION_KEY, {})

    def _save(self):
        self.session.modified = True

    def add(self, produit, qte=1):
        pid = str(produit.pk)
        self.items[pid] = self.items.get(pid, 0) + qte
        self._save()

    def set_quantite(self, produit_id, qte):
        pid = str(produit_id)
        if qte <= 0:
            self.items.pop(pid, None)
        else:
            self.items[pid] = qte
        self._save()

    def remove(self, produit_id):
        self.items.pop(str(produit_id), None)
        self._save()

    def clear(self):
        self.items = self.session[SESSION_KEY] = {}
        self._save()

    def __iter__(self):
        """Hydrate chaque entrée en `{produit, quantite, sous_total_cents}`.

        Les produits dépubliés ou supprimés disparaissent du chapeau au passage.
        """
        produits = {str(p.pk): p for p in Produit.objects.filter(id__in=self.items, publie=True)}
        stale = [pid for pid in self.items if pid not in produits]
        if stale:
            for pid in stale:
                self.items.pop(pid)
            self._save()
        for pid, produit in produits.items():
            qte = self.items[pid]
            yield {"produit": produit, "quantite": qte, "sous_total_cents": produit.prix_cents * qte}

    def __len__(self):
        """Nombre total d'articles (pour le badge)."""
        return sum(self.items.values())

    def __bool__(self):
        return bool(self.items)

    @property
    def lignes(self):
        return list(self)

    @property
    def montant_articles_cents(self):
        return sum(ligne["sous_total_cents"] for ligne in self)
