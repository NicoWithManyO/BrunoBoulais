"""Sanitize-on-render filters for content authored via the RichText widget.

We deliberately do NOT sanitize on save: the editor stores whatever HTML the
browser emits, and bleach gates what reaches the page. Whitelist changes don't
need data migrations this way, and a compromised staff account can't poison
the DB into rendering scripts (they'd still need to break bleach).
"""
import html
import re

import bleach
from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

# Block mode keeps <p> so paragraphs render. Inline mode strips <p>: useful
# when the surrounding template already provides the block container (e.g.
# inside an <h1> or an inline pull-quote).
_BLOCK_TAGS = frozenset({"p", "br", "strong", "em", "ul", "ol", "li"})
_INLINE_TAGS = frozenset({"br", "strong", "em"})

# Repère d'insertion d'une image dans le corps d'une actu. On absorbe le <p>
# qui enveloppe un repère seul (sinon la <figure>, élément bloc, se retrouverait
# imbriquée dans un <p> → HTML invalide) ; un repère inline est remplacé tel
# quel. L'absorption est tout-ou-rien pour ne jamais laisser de balise orpheline.
_IMAGE_MARKER_RE = re.compile(r"<p>\s*\[image:(\d+)\]\s*</p>|\[image:(\d+)\]")


@register.filter(name="richtext")
def richtext(value, mode="block"):
    if not value:
        return ""
    tags = _BLOCK_TAGS if mode == "block" else _INLINE_TAGS
    cleaned = bleach.clean(value, tags=tags, attributes={}, strip=True)
    return mark_safe(cleaned)


@register.filter(name="richtext_plain")
def richtext_plain(value):
    """Strip every tag. Use in lists/admin tables before truncatechars."""
    if not value:
        return ""
    return bleach.clean(value, tags=set(), attributes={}, strip=True)


@register.filter(name="richtext_images")
def richtext_images(value, images):
    """Comme `richtext` (mode block), mais remplace chaque repère `[image:N]`
    par une figure légendée cliquable (N = l'« Ordre »/`position` de l'image
    dans le lot « contenu »). `images` = itérable d'OrderedImage. Repère sans
    image correspondante : laissé tel quel."""
    if not value:
        return ""
    cleaned = bleach.clean(value, tags=_BLOCK_TAGS, attributes={}, strip=True)
    by_position = {img.position: img for img in images}

    def replace(match):
        position = int(match.group(1) or match.group(2))
        img = by_position.get(position)
        return _figure(img) if img is not None else match.group(0)

    return mark_safe(_IMAGE_MARKER_RE.sub(replace, cleaned))


def _plain_text(value):
    """Texte brut (balises retirées, entités décodées) prêt à ré-échapper une
    seule fois. bleach échappe les entités ; on les décode pour éviter le
    double-échappement quand on repasse par `escape`."""
    if not value:
        return ""
    return html.unescape(bleach.clean(value, tags=set(), attributes={}, strip=True))


def _figure(img):
    url = escape(img.image.url)
    legende_plain = _plain_text(img.legende)
    alt = escape(img.alt or legende_plain)
    # Largeur + alignement optionnels (images de contenu du carnet). 100 =
    # pleine largeur ; center = bloc centré (défaut). gauche/droite flottent
    # pour laisser le texte s'enrouler. Tout est géré par des classes CSS,
    # le ratio reste préservé (width:100% / height:auto sur l'<img>).
    classes = ["news-img"]
    largeur = getattr(img, "largeur", "100")
    if largeur != "100":
        classes.append(f"news-img--w{largeur}")
    alignement = getattr(img, "alignement", "center")
    if alignement in ("left", "right"):
        classes.append(f"news-img--{alignement}")
    css_class = " ".join(classes)
    parts = [
        f'<figure class="{css_class}">'
        f'<a href="{url}" data-lightbox-trigger data-lightbox-src="{url}" '
        f'data-lightbox-caption="{escape(legende_plain)}" data-lightbox-alt="{alt}" '
        f'target="_blank" rel="noopener">'
        f'<img src="{url}" alt="{alt}" loading="lazy" decoding="async"></a>'
    ]
    if img.legende:
        legende_html = bleach.clean(img.legende, tags=_INLINE_TAGS, attributes={}, strip=True)
        parts.append(f"<figcaption>{legende_html}</figcaption>")
    parts.append("</figure>")
    return "".join(parts)
