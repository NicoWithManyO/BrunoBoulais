"""Validators for user-uploaded media."""
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

MAX_IMAGE_SIZE_MB = 8
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024

ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "avif"]

image_extension_validator = FileExtensionValidator(allowed_extensions=ALLOWED_IMAGE_EXTENSIONS)


def validate_image_size(file):
    """Reject images larger than MAX_IMAGE_SIZE_BYTES."""
    if file.size > MAX_IMAGE_SIZE_BYTES:
        raise ValidationError(
            f"L'image dépasse {MAX_IMAGE_SIZE_MB} Mo "
            f"(taille actuelle : {file.size / 1024 / 1024:.1f} Mo)."
        )


IMAGE_VALIDATORS = [image_extension_validator, validate_image_size]
