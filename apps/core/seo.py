"""Build SEO context dicts to merge into ``render(..., {...})`` calls.

The output is consumed by ``templates/base.html`` which reads
``seo_title`` / ``seo_description`` / ``seo_og_image`` / ``seo_og_type``
with ``|default:default_seo_*`` fallbacks supplied by ``site_context``.

Only non-empty keys are emitted so the defaults fall through cleanly.
"""
from __future__ import annotations


def _resolve_og_image(request, value):
    """Coerce a string URL or a FieldFile into an absolute URL, or None."""
    if not value:
        return None
    if isinstance(value, str):
        return value
    # FieldFile / ImageFieldFile: ``.name`` is empty when no file is attached.
    # We must NOT touch ``.url`` blindly — Django raises ValueError for empty
    # files, which hasattr() does not swallow (it only catches AttributeError).
    if not getattr(value, "name", None):
        return None
    return request.build_absolute_uri(value.url)


def seo(request, *, title=None, description=None, og_image=None, og_type=None):
    """Build a partial SEO context.

    ``og_image`` accepts either a FieldFile (ImageField value) or a string URL.
    Falsy / unattached values are dropped so the site-wide defaults fall through.
    """
    out = {}
    if title:
        out["seo_title"] = title
    if description:
        out["seo_description"] = description
    img_url = _resolve_og_image(request, og_image)
    if img_url:
        out["seo_og_image"] = img_url
    if og_type:
        out["seo_og_type"] = og_type
    return out


def seo_from_obj(request, obj, *, title_fallback=None, description_fallback=None, og_type=None):
    """Read seo_title/seo_description/og_image off a SeoMixin instance."""
    return seo(
        request,
        title=(getattr(obj, "seo_title", "") or title_fallback) if obj else title_fallback,
        description=(getattr(obj, "seo_description", "") or description_fallback) if obj else description_fallback,
        og_image=getattr(obj, "og_image", None) if obj else None,
        og_type=og_type,
    )
