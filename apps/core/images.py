"""Image processing helpers — used by gestion forms to strip EXIF metadata."""
from io import BytesIO

from django.core.files.uploadedfile import InMemoryUploadedFile
from PIL import Image

# Mapping Pillow format ↔ MIME type / extension.
_PIL_FORMAT_BY_EXT = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
    "avif": "AVIF",
}


def strip_exif(uploaded_file):
    """Return a new InMemoryUploadedFile with EXIF metadata removed.

    Re-encodes the image via Pillow, copying only the pixel data — EXIF, GPS,
    and other sidecar metadata are dropped. Returns the input unchanged if
    Pillow can't read it (e.g. unsupported format, broken file).
    """
    name = getattr(uploaded_file, "name", "") or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    pil_format = _PIL_FORMAT_BY_EXT.get(ext)
    if not pil_format:
        return uploaded_file

    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as img:
            img.load()
            data = list(img.getdata())
            mode = img.mode
            size = img.size

        clean = Image.new(mode, size)
        clean.putdata(data)

        buf = BytesIO()
        save_kwargs = {}
        if pil_format == "JPEG":
            save_kwargs["quality"] = 88
            save_kwargs["optimize"] = True
            if mode in ("RGBA", "P"):
                clean = clean.convert("RGB")
        clean.save(buf, format=pil_format, **save_kwargs)
        buf.seek(0)

        return InMemoryUploadedFile(
            file=buf,
            field_name=getattr(uploaded_file, "field_name", None),
            name=name,
            content_type=uploaded_file.content_type if hasattr(uploaded_file, "content_type") else None,
            size=buf.getbuffer().nbytes,
            charset=None,
        )
    except Exception:
        # If Pillow chokes, keep the original — the FileExtensionValidator and
        # ImageField's internal validation will reject genuinely bad files.
        uploaded_file.seek(0)
        return uploaded_file
