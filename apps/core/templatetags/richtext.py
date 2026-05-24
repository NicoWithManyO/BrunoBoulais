"""Sanitize-on-render filters for content authored via the RichText widget.

We deliberately do NOT sanitize on save: the editor stores whatever HTML the
browser emits, and bleach gates what reaches the page. Whitelist changes don't
need data migrations this way, and a compromised staff account can't poison
the DB into rendering scripts (they'd still need to break bleach).
"""
import bleach
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Block mode keeps <p> so paragraphs render. Inline mode strips <p>: useful
# when the surrounding template already provides the block container (e.g.
# inside an <h1> or an inline pull-quote).
_BLOCK_TAGS = frozenset({"p", "br", "strong", "em", "ul", "ol", "li"})
_INLINE_TAGS = frozenset({"br", "strong", "em"})


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
