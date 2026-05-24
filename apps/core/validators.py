"""Validators for user-uploaded media."""
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

MAX_IMAGE_SIZE_MB = 8
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024

MAX_VIDEO_SIZE_MB = 50
MAX_VIDEO_SIZE_BYTES = MAX_VIDEO_SIZE_MB * 1024 * 1024

ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "avif"]
ALLOWED_VIDEO_EXTENSIONS = ["mp4", "webm", "mov"]
ALLOWED_MEDIA_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS + ALLOWED_VIDEO_EXTENSIONS

image_extension_validator = FileExtensionValidator(allowed_extensions=ALLOWED_IMAGE_EXTENSIONS)
media_extension_validator = FileExtensionValidator(allowed_extensions=ALLOWED_MEDIA_EXTENSIONS)


def validate_image_size(file):
    """Reject images larger than MAX_IMAGE_SIZE_BYTES."""
    if file.size > MAX_IMAGE_SIZE_BYTES:
        raise ValidationError(
            f"L'image dépasse {MAX_IMAGE_SIZE_MB} Mo "
            f"(taille actuelle : {file.size / 1024 / 1024:.1f} Mo)."
        )


def validate_media_size(file):
    """Cap selon le type déduit de l'extension : 8 Mo pour image, 50 Mo pour vidéo."""
    ext = Path(getattr(file, "name", "")).suffix.lower().lstrip(".")
    if ext in ALLOWED_VIDEO_EXTENSIONS:
        cap_mb, cap_bytes = MAX_VIDEO_SIZE_MB, MAX_VIDEO_SIZE_BYTES
        label = "La vidéo"
    else:
        cap_mb, cap_bytes = MAX_IMAGE_SIZE_MB, MAX_IMAGE_SIZE_BYTES
        label = "L'image"
    if file.size > cap_bytes:
        raise ValidationError(
            f"{label} dépasse {cap_mb} Mo "
            f"(taille actuelle : {file.size / 1024 / 1024:.1f} Mo)."
        )


IMAGE_VALIDATORS = [image_extension_validator, validate_image_size]
MEDIA_VALIDATORS = [media_extension_validator, validate_media_size]
