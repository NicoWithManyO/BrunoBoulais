"""Generate the open-graph default image used in social link previews,
and the nav hat asset derived from its raw source.

Re-run manually after editing the OG card design or replacing the hat
source. The outputs (``static/img/og-default.jpg`` and
``static/img/chapeau-bruno-nav.png``) are committed and shipped via
Whitenoise.

Les favicons (chapeau de Bruno) sont des assets dessinés à la main,
PAS générés par ce script — ne pas les régénérer ici.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "static" / "img"
SOURCES = ROOT / "sources"

TERRACOTTA = (201, 98, 43)
CREAM = (245, 239, 230)
BROWN = (92, 58, 33)
INK = (43, 43, 43)
SLATE = (74, 100, 128)

SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
SERIF_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
SERIF_ITALIC = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf"


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
    draw.text((220, 540), "jacques-bertin.manyo.dev", font=eyebrow_font, fill=SLATE)

    return img


def _nav_hat() -> None:
    """Dérive l'asset nav du chapeau depuis sa source brute (RGBA, fond transparent)."""
    source = SOURCES / "chapeau-bruno.png"
    if not source.exists():
        # sources/ est gitignoré : la source n'existe que sur la machine de Bruno.
        print(f"  skip {source.relative_to(ROOT)} absent — chapeau nav non régénéré")
        return

    img = Image.open(source)
    # Recadrage sur le chapeau : seuil sur l'alpha car la source contient du
    # bruit quasi transparent sur toute la surface, qui fausserait getbbox().
    mask = img.getchannel("A").point(lambda v: 255 if v > 30 else 0)
    left, top, right, bottom = mask.getbbox()
    margin = 8  # marge pour ne pas couper l'anticrénelage du bord
    hat = img.crop((
        max(left - margin, 0),
        max(top - margin, 0),
        min(right + margin, img.width),
        min(bottom + margin, img.height),
    ))
    # 2× la plus grande taille d'affichage CSS (.brand-hat : 88×60) pour le retina.
    width = 176
    height = round(width * hat.height / hat.width)
    hat = hat.resize((width, height), Image.LANCZOS)

    path = IMG / "chapeau-bruno-nav.png"
    hat.save(path, optimize=True)
    print(f"  wrote {path.relative_to(ROOT)} ({width}×{height})")


def main():
    IMG.mkdir(parents=True, exist_ok=True)
    path = IMG / "og-default.jpg"
    _og_default().save(path, "JPEG", quality=88, progressive=True, optimize=True)
    print(f"  wrote {path.relative_to(ROOT)} (1200×630)")
    _nav_hat()


if __name__ == "__main__":
    main()
