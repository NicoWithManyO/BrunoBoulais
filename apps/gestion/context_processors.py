"""Context processors for the unread-message count (gestion badge + navbar hat)."""
from apps.contact.models import Message


def gestion_context(request):
    """Inject unread message count for the gestion sidebar badge and the navbar hat indicator.

    The hat indicator is shown site-wide so Bruno spots it while browsing the
    public site without being logged in — a wiggling hat only means something to
    him. Skips the COUNT query on POST/redirects.
    """
    if request.method != "GET":
        return {}
    return {
        "unread_messages_count": Message.objects.filter(lu=False, archive=False).count(),
    }
