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


def ocr_source(data: bytes, mime: str, workdir: Path) -> Path:
    """Full-quality image of the receipt for OCR (PDF -> first page at 200 dpi)."""
    out = Path(workdir) / "receipt.png"
    if mime == "application/pdf" or data[:5] == b"%PDF-":
        from pdf2image import convert_from_bytes
        pages = convert_from_bytes(data, dpi=200, first_page=1, last_page=1)
        img = pages[0] if pages else Image.new("RGB", (800, 1000), "white")
    else:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.save(out, "PNG")
    return out


def trash_original(data: bytes, orig_filename: str, stem: str) -> Path:
    """Keep the original receipt in the trash folder (auto-cleared later)."""
    settings.trash_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(orig_filename).suffix or ".bin"
    out = settings.trash_dir / f"{stem}{ext}"
    out.write_bytes(data)
    return out


QR_MAX_BYTES = 8 * 1024 * 1024


def save_qr_image(data: bytes, event_id: int) -> str:
    """Validate an uploaded payment QR (PNG/JPG/WebP) and store it as PNG.

    Returns the public URL path (/qr/<file>). Raises ValueError if not an image.
    PNG keeps the QR modules sharp; the image is only downscaled if huge.
    """
    if not data or len(data) > QR_MAX_BYTES:
        raise ValueError("size")
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("not_image") from exc
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L", "RGBA"):
        img = img.convert("RGB")
    img.thumbnail((1600, 1600))
    settings.qr_dir.mkdir(parents=True, exist_ok=True)
    name = f"event-{int(event_id)}-{_hash(data)[:10]}.png"
    img.save(settings.qr_dir / name, "PNG", optimize=True)
    return f"/qr/{name}"


SLIDE_MAX_BYTES = 25 * 1024 * 1024
SLIDE_MAX = 2000     # px, long edge for home-page carousel images


def save_slide_image(data: bytes) -> str:
    """Validate an uploaded carousel photo and store it as WebP.

    Returns the stored file name (under settings.slides_dir). Raises ValueError
    if the upload is empty, too large or not an image.
    """
    if not data or len(data) > SLIDE_MAX_BYTES:
        raise ValueError("size")
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("not_image") from exc
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((SLIDE_MAX, SLIDE_MAX))
    settings.slides_dir.mkdir(parents=True, exist_ok=True)
    name = f"slide-{_hash(data)}.webp"
    img.save(settings.slides_dir / name, "WEBP", quality=82, method=5)
    return name
