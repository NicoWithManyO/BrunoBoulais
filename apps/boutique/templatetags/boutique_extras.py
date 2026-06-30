from django import template

from ..pricing import montant_euros

register = template.Library()


@register.filter
def euros(cents):
    """Formate des centimes en montant FR : 2410 → "24,10 €"."""
    try:
        return montant_euros(int(cents))
    except (TypeError, ValueError):
        return ""
