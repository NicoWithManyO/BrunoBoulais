from django.conf import settings
from django.core.cache import cache
from django.db import OperationalError, ProgrammingError
from django.templatetags.static import static

from apps.core.models import VisiteJournaliere
from apps.parametres.models import Parametres

SITE_NAME = "Bruno Boulais — auteur"
BOOK_TITLE = "Jacques Bertin, le géant discret de la chanson"
DEFAULT_SEO_TITLE = f"{SITE_NAME} — {BOOK_TITLE}"
DEFAULT_SEO_DESCRIPTION = (
    "Site officiel de Bruno Boulais, auteur de « Jacques Bertin, le géant discret"
    " de la chanson » paru aux Éditions du Petit Pavé."
)


def site_context(request):
    host_url = f"{request.scheme}://{request.get_host()}"
    default_og_image = host_url + static("img/og-default.jpg")
    try:
        parametres = Parametres.get_solo()
    except (OperationalError, ProgrammingError):
        # DB locked / table missing (fresh checkout, backup, migrate) :
        # on dégrade gracieusement pour ne pas casser 500.html.
        parametres = None

    total_visiteurs = cache.get("total_visiteurs")
    if total_visiteurs is None:
        try:
            total_visiteurs = VisiteJournaliere.objects.count()
        except (OperationalError, ProgrammingError):
            total_visiteurs = 0
        cache.set("total_visiteurs", total_visiteurs, 60)

    return {
        "SITE_NAME": SITE_NAME,
        "BOOK_TITLE": BOOK_TITLE,
        "CONTACT_EMAIL": getattr(settings, "CONTACT_EMAIL", ""),
        "default_seo_title": DEFAULT_SEO_TITLE,
        "default_seo_description": DEFAULT_SEO_DESCRIPTION,
        "default_seo_og_image": default_og_image,
        "parametres": parametres,
        "total_visiteurs": total_visiteurs,
    }
