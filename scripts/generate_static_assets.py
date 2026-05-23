"""Generate favicon PNGs + open-graph default image from the SVG sources.

Re-run manually after touching the brand palette or the favicon design.
Outputs land in ``static/`` and are committed (they ship to Whitenoise).
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
IMG = STATIC / "img"

TERRACOTTA = (201, 98, 43)
CREAM = (245, 239, 230)
SAND = (232, 220, 196)
BROWN = (92, 58, 33)
INK = (43, 43, 43)
SLATE = (74, 100, 128)

SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
SERIF_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
SERIF_ITALIC = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf"


def _favicon(size: int, *, radius_ratio: float = 0.1875, maskable: bool = False) -> Image.Image:
    """Render the brand favicon at the given size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = int(size * radius_ratio)
    if maskable:
        # Maskable icons need a full-bleed background (safe zone is the inner 80%).
        draw.rectangle([(0, 0), (size, size)], fill=TERRACOTTA + (255,))
    else:
        draw.rounded_rectangle([(0, 0), (size - 1, size - 1)], radius=radius, fill=TERRACOTTA + (255,))

    glyph_size = int(size * 0.72)
    font = ImageFont.truetype(SERIF, glyph_size)
    bbox = draw.textbbox((0, 0), "B", font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - text_w) / 2 - bbox[0]
    y = (size - text_h) / 2 - bbox[1] - size * 0.04  # optical centering nudge
    draw.text((x, y), "B", font=font, fill=CREAM + (255,))
    return img


def _og_default() -> Image.Image:
    """1200×630 landing image for social cards. Cream stage, terracotta strip."""
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(img)

    # Left terracotta band evoking a book spine.
    draw.rectangle([(0, 0), (140, H)], fill=TERRACOTTA)

    # Subtle horizontal rule under the title.
    draw.rectangle([(220, 410), (340, 414)], fill=TERRACOTTA)

    eyebrow_font = ImageFont.truetype(SERIF, 26)
    title_font = ImageFont.truetype(SERIF_BOLD, 64)
    italic_font = ImageFont.truetype(SERIF_ITALIC, 48)
    author_font = ImageFont.truetype(SERIF, 30)

    draw.text((220, 160), "BRUNO BOULAIS PRÉSENTE", font=eyebrow_font, fill=SLATE)

    # Two-line title.
    draw.text((220, 220), "Jacques Bertin,", font=title_font, fill=BROWN)

    # Subtitle assembled by chaining measured segments so spaces survive.
    subtitle_y = 310
    x = 220
    segments = [
        ("le ", italic_font, INK),
        ("géant discret ", italic_font, TERRACOTTA),
        ("de la chanson", italic_font, INK),
    ]
    for text, font, color in segments:
        draw.text((x, subtitle_y), text, font=font, fill=color)
        x += int(draw.textlength(text, font=font))

    draw.text((220, 460), "Une biographie aux Éditions du Petit Pavé", font=author_font, fill=INK)

    # Bottom signature line.
    draw.text((220, 540), "brunoboulais.fr", font=eyebrow_font, fill=SLATE)

    return img


def main():
    STATIC.mkdir(exist_ok=True)
    IMG.mkdir(exist_ok=True)

    for size, name in [
        (16, "favicon-16.png"),
        (32, "favicon-32.png"),
        (180, "apple-touch-icon.png"),
        (192, "favicon-192.png"),
        (512, "favicon-512.png"),
    ]:
        path = STATIC / name
        _favicon(size).save(path, "PNG", optimize=True)
        print(f"  wrote {path.relative_to(ROOT)} ({size}px)")

    path = STATIC / "favicon-512-maskable.png"
    _favicon(512, maskable=True).save(path, "PNG", optimize=True)
    print(f"  wrote {path.relative_to(ROOT)} (512px, maskable)")

    path = IMG / "og-default.jpg"
    _og_default().save(path, "JPEG", quality=88, progressive=True, optimize=True)
    print(f"  wrote {path.relative_to(ROOT)} (1200×630)")


if __name__ == "__main__":
    main()
