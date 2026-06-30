from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.seo import seo

from .cart import Chapeau
from .models import BoutiquePage, Produit
from .pricing import montant_euros


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
