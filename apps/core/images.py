"""Image processing helpers — used by gestion forms to strip EXIF metadata."""
import logging
from io import BytesIO

from django.core.files.uploadedfile import InMemoryUploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.core.validators import MAX_IMAGE_SIZE_BYTES

logger = logging.getLogger(__name__)

_PIL_FORMAT_BY_EXT = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
    "avif": "AVIF",
}


def strip_exif(uploaded_file):
    """Return a new InMemoryUploadedFile with EXIF metadata removed.

    Re-encodes via Pillow with ``exif=b""``. For static images, ``exif_transpose``
    first bakes the orientation tag into the pixels so phone photos don't end up
    rotated. Animated PNG/WEBP/AVIF keep all frames (no transpose — it would
    flatten the animation to frame 0). If Pillow can't read or save the file,
    we log and return the original; the FileExtensionValidator and ImageField
    still gate genuinely broken uploads upstream.
    """
    name = getattr(uploaded_file, "name", "") or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    pil_format = _PIL_FORMAT_BY_EXT.get(ext)
    if not pil_format:
        return uploaded_file

    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as img:
            is_animated = getattr(img, "is_animated", False)
            save_kwargs = {"format": pil_format, "exif": b""}

            if is_animated and pil_format in ("PNG", "WEBP", "AVIF"):
                save_kwargs["save_all"] = True
                target = img
            else:
                target = ImageOps.exif_transpose(img)

            if pil_format == "JPEG":
                save_kwargs["quality"] = 92
                save_kwargs["optimize"] = True
                save_kwargs["progressive"] = True
                if target.mode not in ("RGB", "L"):
                    target = target.convert("RGB")

            buf = BytesIO()
            target.save(buf, **save_kwargs)
            buf.seek(0)

        # validate_image_size only saw the original upload. If re-encoding
        # at q=92 + progressive grew the file past the validator limit
        # (rare but possible with already-aggressive sources), keep the
        # original — it has EXIF but at least respects the storage budget.
        if buf.getbuffer().nbytes > MAX_IMAGE_SIZE_BYTES:
            logger.warning(
                "strip_exif: re-encoded %r grew past %d bytes, keeping original",
                name, MAX_IMAGE_SIZE_BYTES,
            )
            uploaded_file.seek(0)
            return uploaded_file

        return InMemoryUploadedFile(
            file=buf,
            field_name=getattr(uploaded_file, "field_name", None),
            name=name,
            content_type=getattr(uploaded_file, "content_type", None),
            size=buf.getbuffer().nbytes,
            charset=None,
        )
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        logger.warning("strip_exif: keeping original %r (%s)", name, exc)
        uploaded_file.seek(0)
        return uploaded_file
