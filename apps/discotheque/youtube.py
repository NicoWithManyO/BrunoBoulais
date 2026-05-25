"""Auto-remplissage des champs Chanson depuis YouTube oEmbed.

Récupère le titre et la miniature publique d'une vidéo YouTube via
l'endpoint oEmbed (`https://www.youtube.com/oembed`) — public, sans clé
API. En cas d'échec (timeout, vidéo privée, réseau down), les fonctions
retournent None : l'auto-fill est best-effort, le save de la chanson
doit toujours réussir et l'utilisateur peut saisir les champs à la main.
"""
import json
import logging
import re
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

OEMBED_ENDPOINT = "https://www.youtube.com/oembed"
TIMEOUT_SECONDS = 5
# Cap large pour une miniature YT (les `maxresdefault.jpg` font ~50-300 Ko).
MAX_THUMBNAIL_BYTES = 5 * 1024 * 1024
_USER_AGENT = "BrunoBoulais/1.0 (+oembed-autofill)"

# Les titres oEmbed ont quasi-systématiquement la forme
# « Jacques Bertin - <Titre> » (ou « – », « — », « : », « | »). On retire le
# préfixe puisque tout le site parle déjà de Jacques Bertin (cf. UX choisie
# par Bruno).
_ARTIST_PREFIX_RE = re.compile(
    r"^\s*Jacques\s+Bertin\s*[-–—:|]+\s*",
    re.IGNORECASE,
)


def strip_artist_prefix(title):
    if not title:
        return title
    return _ARTIST_PREFIX_RE.sub("", title).strip()


def fetch_oembed(url_youtube):
    """Retourne `{"title", "thumbnail_url"}` pour une URL YouTube, ou None."""
    if not url_youtube:
        return None
    qs = urlencode({"url": url_youtube, "format": "json"})
    try:
        req = Request(f"{OEMBED_ENDPOINT}?{qs}", headers={"User-Agent": _USER_AGENT})
        with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (URLError, OSError, ValueError) as exc:
        logger.info("oEmbed YouTube indisponible pour %s (%s)", url_youtube, exc)
        return None
    title = strip_artist_prefix((data.get("title") or "").strip()) or None
    thumbnail = (data.get("thumbnail_url") or "").strip() or None
    if not title and not thumbnail:
        return None
    return {"title": title, "thumbnail_url": thumbnail}


def download_thumbnail(url):
    """Télécharge une miniature, retourne `(name, bytes)` ou `(None, None)`.

    Cap dur à MAX_THUMBNAIL_BYTES pour rester sous IMAGE_VALIDATORS et
    éviter qu'un endpoint malveillant ne sature la mémoire.
    """
    if not url:
        return None, None
    try:
        req = Request(url, headers={"User-Agent": _USER_AGENT})
        with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            content = resp.read(MAX_THUMBNAIL_BYTES + 1)
    except (URLError, OSError) as exc:
        logger.info("Thumbnail YouTube indisponible (%s : %s)", url, exc)
        return None, None
    if not content or len(content) > MAX_THUMBNAIL_BYTES:
        logger.info("Thumbnail YouTube vide ou trop volumineuse (%s)", url)
        return None, None
    # Les miniatures YT sont toujours en JPG, on force l'extension.
    return "yt-thumbnail.jpg", content
