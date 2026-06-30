from .cart import Chapeau


def chapeau_context(request):
    """Expose le nombre d'articles du chapeau pour le badge du header."""
    return {"chapeau_count": len(Chapeau(request))}
