"""Image processing: gallery previews and receipt compression.

- Previews: WebP thumb + large preview, cached locally under DATA_DIR/cache.
  Originals are NOT kept — only these previews.
- Receipts: incoming PNG/JPG/PDF converted to WebP at a configurable quality;
  the original file is moved to the trash folder (auto-cleared after N days).
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image, ImageOps

from .config import settings

THUMB_MAX = 500      # px, grid thumbnail (long edge)
PREVIEW_MAX = 1600   # px, large preview (long edge)


def _hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:20]


def make_previews(original: bytes) -> dict:
    """Return {thumb_path, preview_path, width, height} (paths relative to DATA_DIR)."""
    img = Image.open(io.BytesIO(original))
    img = ImageOps.exif_transpose(img)  # honour camera orientation
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    key = _hash(original)

    thumbs = settings.cache_dir / "thumbs"
    previews = settings.cache_dir / "previews"
    thumbs.mkdir(parents=True, exist_ok=True)
    previews.mkdir(parents=True, exist_ok=True)

    thumb = img.copy()
    thumb.thumbnail((THUMB_MAX, THUMB_MAX))
    thumb_path = thumbs / f"{key}.webp"
    thumb.save(thumb_path, "WEBP", quality=72, method=5)

    prev = img.copy()
    prev.thumbnail((PREVIEW_MAX, PREVIEW_MAX))
    preview_path = previews / f"{key}.webp"
    prev.save(preview_path, "WEBP", quality=80, method=5)

    return {
        "thumb_path": str(thumb_path.relative_to(settings.data_path)),
        "preview_path": str(preview_path.relative_to(settings.data_path)),
        "width": w,
        "height": h,
    }


def receipt_to_webp(data: bytes, mime: str, stem: str) -> Path:
    """Compress a receipt to WebP (first PDF page included). Returns stored path."""
    settings.receipts_dir.mkdir(parents=True, exist_ok=True)
    out = settings.receipts_dir / f"{stem}.webp"

    if mime == "application/pdf" or data[:5] == b"%PDF-":
        from pdf2image import convert_from_bytes
        pages = convert_from_bytes(data, dpi=150, first_page=1, last_page=1)
        img = pages[0] if pages else Image.new("RGB", (800, 1000), "white")
    else:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((2000, 2000))
    img.save(out, "WEBP", quality=settings.receipt_webp_quality, method=5)
    return out


def trash_original(data: bytes, orig_filename: str, stem: str) -> Path:
    """Keep the original receipt in the trash folder (auto-cleared later)."""
    settings.trash_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(orig_filename).suffix or ".bin"
    out = settings.trash_dir / f"{stem}{ext}"
    out.write_bytes(data)
    return out
