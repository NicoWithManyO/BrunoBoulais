"""Context processors specific to /gestion/."""
from apps.contact.models import Message


def gestion_context(request):
    """Inject unread message count for the gestion sidebar badge.

    Only runs the COUNT query on GET requests that actually render the layout —
    skips POST/redirects and unauthenticated visitors.
    """
    if request.method != "GET":
        return {}
    if not request.path.startswith("/gestion/") or not request.user.is_authenticated:
        return {}
    return {
        "unread_messages_count": Message.objects.filter(lu=False, archive=False).count(),
    }
