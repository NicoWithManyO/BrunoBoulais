"""Schema.org JSON-LD helpers for SEO."""
import json

from django import template
from django.utils.safestring import mark_safe

from apps.core.context_processors import BOOK_TITLE, SITE_NAME

register = template.Library()


def _render(data):
    """Serialize a dict as a <script type=\"application/ld+json\"> block."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # Escape "</" sequences to avoid prematurely closing the <script>.
    payload = payload.replace("</", "<\\/")
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')


def _abs(request, url):
    return request.build_absolute_uri(url) if url else None


@register.simple_tag(takes_context=True)
def website_jsonld(context):
    """schema.org/WebSite — used on the home page."""
    request = context["request"]
    return _render({
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": _abs(request, "/"),
        "inLanguage": "fr-FR",
        "about": {
            "@type": "Book",
            "name": BOOK_TITLE,
            "author": {"@type": "Person", "name": "Bruno Boulais"},
        },
    })


@register.simple_tag(takes_context=True)
def book_jsonld(context, livre=None):
    """schema.org/Book — used on /le-livre/."""
    request = context["request"]
    data = {
        "@context": "https://schema.org",
        "@type": "Book",
        "name": BOOK_TITLE,
        "author": {"@type": "Person", "name": "Bruno Boulais"},
        "inLanguage": "fr",
        "publisher": {"@type": "Organization", "name": "Éditions du Petit Pavé"},
        "bookFormat": "https://schema.org/Paperback",
    }
    if livre:
        cover = livre.images.first() if hasattr(livre, "images") else None
        if cover and cover.image:
            data["image"] = _abs(request, cover.image.url)
        if getattr(livre, "pitch_court", ""):
            # Strip HTML tags from the rich text pitch.
            import bleach
            data["abstract"] = bleach.clean(livre.pitch_court, tags=set(), strip=True)[:300]
    return _render(data)


@register.simple_tag(takes_context=True)
def person_jsonld(context, personne, role):
    """schema.org/Person — used on /jacques-bertin/ and /l-auteur/.

    `role` is "sujet" (= Bertin) or "auteur" (= Bruno) — used to set sensible
    defaults that don't depend on the DB record being populated.
    """
    request = context["request"]
    defaults_by_role = {
        "sujet": {
            "name": "Jacques Bertin",
            "jobTitle": "Chanteur, poète, écrivain",
            "birthDate": "1946",
            "birthPlace": {"@type": "Place", "name": "Rennes, France"},
            "nationality": {"@type": "Country", "name": "France"},
        },
        "auteur": {
            "name": "Bruno Boulais",
            "jobTitle": "Auteur, biographe",
            "nationality": {"@type": "Country", "name": "France"},
        },
    }
    data = {"@context": "https://schema.org", "@type": "Person"}
    data.update(defaults_by_role.get(role, {}))
    if personne:
        if getattr(personne, "nom", ""):
            data["name"] = personne.nom
        if getattr(personne, "bio_courte", ""):
            import bleach
            data["description"] = bleach.clean(personne.bio_courte, tags=set(), strip=True)[:300]
        portrait = personne.images.first() if hasattr(personne, "images") else None
        if portrait and portrait.image:
            data["image"] = _abs(request, portrait.image.url)
    return _render(data)
