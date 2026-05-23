from django.conf import settings


def site_context(request):
    return {
        "SITE_NAME": "Bruno Boulais — auteur",
        "BOOK_TITLE": "Jacques Bertin, le géant discret de la chanson",
        "CONTACT_EMAIL": getattr(settings, "CONTACT_EMAIL", ""),
    }
