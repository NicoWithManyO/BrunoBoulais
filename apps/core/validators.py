"""Validators for user-uploaded media."""
import logging
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

logger = logging.getLogger(__name__)

MAX_IMAGE_SIZE_MB = 8
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024

MAX_VIDEO_SIZE_MB = 50
MAX_VIDEO_SIZE_BYTES = MAX_VIDEO_SIZE_MB * 1024 * 1024

ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "avif"]
ALLOWED_VIDEO_EXTENSIONS = ["mp4", "webm", "mov"]
ALLOWED_MEDIA_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS + ALLOWED_VIDEO_EXTENSIONS

image_extension_validator = FileExtensionValidator(allowed_extensions=ALLOWED_IMAGE_EXTENSIONS)
media_extension_validator = FileExtensionValidator(allowed_extensions=ALLOWED_MEDIA_EXTENSIONS)


def _safe_file_size(file):
    """Retourne file.size ou None si le fichier physique est absent.

    Cas typique : DB prod copiée en dev sans rsync des médias → un FieldFile
    pointe vers un chemin inexistant et file.size déclenche os.path.getsize
    → FileNotFoundError. Django ré-exécute les validators à chaque
    full_clean() (y compris quand le fichier n'a pas été re-uploadé), donc
    un simple POST sur un form qui contient un FileField casse tout. Skip
    propre + log info : en prod nominal ça n'arrive pas (les uploads ne
    sont pas déplacés sous la DB).
    """
    try:
        return file.size
    except FileNotFoundError:
        logger.info(
            "Validator: fichier absent du disque, validation skip (%s)",
            getattr(file, "name", "?"),
        )
        return None


def validate_image_size(file):
    """Reject images larger than MAX_IMAGE_SIZE_BYTES."""
    size = _safe_file_size(file)
    if size is None:
        return
    if size > MAX_IMAGE_SIZE_BYTES:
        raise ValidationError(
            f"L'image dépasse {MAX_IMAGE_SIZE_MB} Mo "
            f"(taille actuelle : {size / 1024 / 1024:.1f} Mo)."
        )


def validate_media_size(file):
    """Cap selon le type déduit de l'extension : 8 Mo pour image, 50 Mo pour vidéo."""
    size = _safe_file_size(file)
    if size is None:
        return
    ext = Path(getattr(file, "name", "")).suffix.lower().lstrip(".")
    if ext in ALLOWED_VIDEO_EXTENSIONS:
        cap_mb, cap_bytes = MAX_VIDEO_SIZE_MB, MAX_VIDEO_SIZE_BYTES
        label = "La vidéo"
    else:
        cap_mb, cap_bytes = MAX_IMAGE_SIZE_MB, MAX_IMAGE_SIZE_BYTES
        label = "L'image"
    if size > cap_bytes:
        raise ValidationError(
            f"{label} dépasse {cap_mb} Mo "
            f"(taille actuelle : {size / 1024 / 1024:.1f} Mo)."
        )


IMAGE_VALIDATORS = [image_extension_validator, validate_image_size]
MEDIA_VALIDATORS = [media_extension_validator, validate_media_size]
