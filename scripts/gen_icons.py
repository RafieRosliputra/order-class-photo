"""Generate placeholder brand assets (logo + PWA icons).

The real JohorStudio.com logos and icons (copied from the johorstudio-website
repo) are committed, so this only fills in anything missing:
    app/static/img/logo-dark.png   (dark logo on light bg)
    app/static/img/logo-light.png  (light logo on dark bg)
Then run this script again (or regenerate icons) if you want icons from the logo.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "app" / "static" / "img"
ICONS = ROOT / "app" / "static" / "icons"
IMG.mkdir(parents=True, exist_ok=True)
ICONS.mkdir(parents=True, exist_ok=True)

SAND = (226, 232, 233)   # --mist
INK = (32, 39, 43)       # --graphite


def _font(size: int):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/Library/Fonts/Arial Bold.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def wordmark(path: Path, fg, bg):
    img = Image.new("RGBA", (520, 120), (0, 0, 0, 0) if bg is None else bg)
    d = ImageDraw.Draw(img)
    d.text((10, 30), "JohorStudio.com", font=_font(54), fill=fg)
    img.save(path)


def icon(path: Path, size: int):
    img = Image.new("RGB", (size, size), INK)
    d = ImageDraw.Draw(img)
    f = _font(int(size * 0.42))
    d.text((size / 2, size / 2), "JS", font=f, fill=SAND, anchor="mm")
    img.save(path)


def placeholder(path: Path):
    img = Image.new("RGB", (600, 800), (243, 240, 236))
    d = ImageDraw.Draw(img)
    d.text((300, 400), "JohorStudio.com", font=_font(34), fill=SAND, anchor="mm")
    img.save(path, "WEBP", quality=70)


def main():
    if not (IMG / "logo-dark.png").exists():
        wordmark(IMG / "logo-dark.png", INK, None)
    if not (IMG / "logo-light.png").exists():
        wordmark(IMG / "logo-light.png", (255, 255, 255), None)
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512)):
        if not (ICONS / name).exists():
            icon(ICONS / name, size)
    if not (IMG / "placeholder.webp").exists():
        placeholder(IMG / "placeholder.webp")
    print("assets written to", IMG, "and", ICONS)


if __name__ == "__main__":
    main()
