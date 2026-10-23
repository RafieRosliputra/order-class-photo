"""Generate placeholder sample photos for the demo: group shots + pose variants.

These are simple illustrative stand-ins (not real photographs) so the demo
gallery has content. Output: data/seed/<CLASS>/<filename>.jpg
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed"

PALETTE = [
    (205, 198, 192), (183, 170, 158), (158, 170, 180), (196, 184, 168),
    (170, 186, 172), (200, 176, 176),
]


def _font(size):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def make_photo(path: Path, label: str, n_people: int, seed: int):
    random.seed(seed)
    W, H = 900, 1200
    bg = PALETTE[seed % len(PALETTE)]
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    # simple "stage" floor
    d.rectangle([0, int(H * 0.72), W, H], fill=tuple(max(0, c - 25) for c in bg))
    # draw simple figures (graduation silhouettes)
    gap = W // (n_people + 1)
    for i in range(n_people):
        cx = gap * (i + 1)
        base = int(H * 0.72)
        robe = (40 + (i * 15) % 60, 40, 60)
        d.ellipse([cx - 34, base - 300, cx + 34, base - 232], fill=(222, 196, 170))  # head
        d.polygon([(cx - 70, base), (cx + 70, base), (cx + 46, base - 240), (cx - 46, base - 240)], fill=robe)  # robe
        d.rectangle([cx - 54, base - 262, cx + 54, base - 250], fill=(20, 20, 24))   # mortarboard brim
        d.polygon([(cx - 60, base - 262), (cx + 60, base - 262), (cx, base - 286)], fill=(20, 20, 24))
    d.text((30, 30), label, font=_font(40), fill=(30, 28, 25))
    d.text((30, H - 60), "SAMPLE — JohorStudio.com", font=_font(26), fill=(90, 86, 80))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=85)


def main():
    classes = ["SK Taman Putra - 6 Bestari", "SK Taman Putra - 6 Cerdik"]
    seed = 1
    for cls in classes:
        folder = SEED / cls
        # one group shot
        make_photo(folder / "DSC_0001.jpg", f"{cls} — Group", 6, seed); seed += 1
        # pose variants (individual / small groups)
        for p in range(2, 9):
            make_photo(folder / f"DSC_000{p}.jpg", f"{cls} — Pose {p-1}", random.randint(1, 3), seed)
            seed += 1
    print("samples written under", SEED)


if __name__ == "__main__":
    main()
