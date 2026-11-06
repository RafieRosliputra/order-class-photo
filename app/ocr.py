"""Receipt OCR: Tesseract reads the text, DeepSeek reads the fields (amount,
reference, date) from that text, regex is the fallback when no API key is set.

`parse_text()` / `merge_ai()` are pure so they are unit-testable. If no text can
be read, callers flag the receipt for manual admin review.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from .config import settings

log = logging.getLogger("ocr")
_paddle = None

BANKS = [
    ("Maybank", r"may\s*bank|maybank2u|mbb"),
    ("CIMB", r"cimb"),
    ("Bank Muamalat", r"muamalat"),
    ("Public Bank", r"public\s*bank|pbe"),
    ("RHB", r"\brhb\b"),
    ("Bank Islam", r"bank\s*islam|bimb"),
    ("Touch 'n Go", r"touch\s*'?n\s*go|tng"),
    ("DuitNow", r"duitnow|duit\s*now"),
]

MONTHS = {
    "jan": 1, "feb": 2, "mac": 3, "mar": 3, "apr": 4, "may": 5, "mei": 5,
    "jun": 6, "jul": 7, "ogo": 8, "aug": 8, "ogos": 8, "sep": 9, "oct": 10,
    "okt": 10, "nov": 11, "dec": 12, "dis": 12,
}

_AMOUNT = re.compile(r"(?:rm|myr)\s*([0-9][0-9,]*\.[0-9]{2})", re.I)
_AMOUNT_LABELLED = re.compile(
    r"(?:amount|jumlah|total|amaun)[^0-9]{0,15}(?:rm|myr)?\s*([0-9][0-9,]*\.[0-9]{2})",
    re.I,
)
_REF = re.compile(
    r"(?:ref(?:erence)?\.?(?:\s*(?:no|id|number))?|transaction\s*(?:id|no)|"
    r"no\.?\s*rujukan|resit|receipt(?:\s*no)?)\.?\s*[:#]?\s*([A-Za-z0-9\-]{6,30})",
    re.I,
)
_DATE_DMY = re.compile(r"\b([0-3]?\d)[/\-.]([01]?\d)[/\-.](20\d{2})\b")
_DATE_YMD = re.compile(r"\b(20\d{2})[/\-.]([01]?\d)[/\-.]([0-3]?\d)\b")
_DATE_TXT = re.compile(r"\b([0-3]?\d)\s*([A-Za-z]{3,4})\s*(20\d{2})\b")
_TIME = re.compile(r"\b([0-2]?\d):([0-5]\d)(?::([0-5]\d))?\s*(am|pm)?\b", re.I)


def _to_sen(amount_str: str) -> int:
    return round(float(amount_str.replace(",", "")) * 100)


def parse_text(text: str) -> dict:
    """Extract fields from raw OCR text. Amount is the largest RM value found."""
    result = {"amount_sen": None, "receipt_no": "", "receipt_date": "",
              "receipt_time": "", "bank": "", "raw": text}

    # amount: prefer a labelled total, else the largest RM value
    amounts = [_to_sen(m) for m in _AMOUNT.findall(text)]
    labelled = _AMOUNT_LABELLED.search(text)
    if labelled:
        result["amount_sen"] = _to_sen(labelled.group(1))
    elif amounts:
        result["amount_sen"] = max(amounts)

    ref = _REF.search(text)
    if ref:
        result["receipt_no"] = ref.group(1).upper()

    # date
    if (m := _DATE_DMY.search(text)):
        d, mth, y = m.groups()
        result["receipt_date"] = _safe_date(int(y), int(mth), int(d))
    elif (m := _DATE_YMD.search(text)):
        y, mth, d = m.groups()
        result["receipt_date"] = _safe_date(int(y), int(mth), int(d))
    elif (m := _DATE_TXT.search(text)):
        d, mon, y = m.groups()
        mth = MONTHS.get(mon.lower()[:3], 0)
        if mth:
            result["receipt_date"] = _safe_date(int(y), mth, int(d))

    if (m := _TIME.search(text)):
        h, mm, ss, ap = m.groups()
        h = int(h)
        if ap and ap.lower() == "pm" and h < 12:
            h += 12
        if ap and ap.lower() == "am" and h == 12:
            h = 0
        result["receipt_time"] = f"{h:02d}:{mm}" + (f":{ss}" if ss else "")

    low = text.lower()
    for name, pat in BANKS:
        if re.search(pat, low):
            result["bank"] = name
            break
    return result


def _safe_date(y: int, m: int, d: int) -> str:
    try:
        return datetime(y, m, d).strftime("%Y-%m-%d")
    except ValueError:
        return ""


# --- text extraction ---------------------------------------------------------
def _prepare_png(src: Path, workdir: Path) -> Path:
    """Grayscale + upscale small screenshots so Tesseract reads digits reliably."""
    from PIL import Image, ImageOps

    img = Image.open(src)
    img = ImageOps.exif_transpose(img)
    img = img.convert("L")
    if img.width < 1200:
        f = 1200 / img.width
        img = img.resize((round(img.width * f), round(img.height * f)), Image.LANCZOS)
    out = workdir / "ocr.png"
    img.save(out, "PNG")
    return out


def _tesseract(png: Path) -> str:
    exe = shutil.which("tesseract")
    if not exe:
        raise RuntimeError("tesseract not installed")
    res = subprocess.run(
        [exe, str(png), "stdout", "-l", settings.ocr_tesseract_lang or "eng", "--psm", "4"],
        capture_output=True, text=True, timeout=90,
    )
    if res.returncode != 0:
        raise RuntimeError(f"tesseract: {res.stderr.strip()[:200]}")
    return res.stdout


def _paddle_text(path: Path) -> str:
    global _paddle
    if _paddle is None:
        from paddleocr import PaddleOCR
        _paddle = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    lines = []
    for page in _paddle.ocr(str(path), cls=True) or []:
        for line in page or []:
            try:
                lines.append(line[1][0])
            except (IndexError, TypeError):
                continue
    return "\n".join(lines)


def extract_text(image_path: str | Path) -> tuple[str, str]:
    """Return (text, engine). Tesseract first; PaddleOCR only if Tesseract is missing."""
    src = Path(image_path)
    with tempfile.TemporaryDirectory() as tmp:
        png = _prepare_png(src, Path(tmp))
        try:
            return _tesseract(png), "tesseract"
        except RuntimeError as exc:
            if "not installed" not in str(exc):
                raise
        return _paddle_text(png), "paddle"


# --- DeepSeek: read fields from OCR text --------------------------------------
_AI_PROMPT = """You read Malaysian bank / e-wallet payment receipts (DuitNow, QR Pay,
IBG/Instant Transfer, Maybank2u, CIMB, TNG...). You get the receipt IMAGE and its
OCR text; trust the image when they disagree. Reply with ONE JSON object only:
{"is_receipt": true/false,          // is this a payment/transfer receipt at all?
 "status": "successful"|"failed"|"pending"|"unknown",
 "amount": "12.50" or null,         // the amount TRANSFERRED, digits only, 2 decimals
 "reference": "..." or "",          // transaction / reference no.
 "date": "YYYY-MM-DD" or "",
 "time": "HH:MM" or "",
 "bank": "..." or "",               // sender's bank / app
 "recipient": "..." or "",          // recipient name if shown
 "note": "short reason if anything looks wrong, else empty"}
Never guess an amount you cannot see on the receipt. Ignore balances, fees and limits."""


def ai_config(conn=None) -> dict:
    """DeepSeek settings: admin page (DB) first, env as fallback."""
    cfg = {"key": settings.deepseek_api_key, "base_url": settings.deepseek_base_url,
           "model": settings.deepseek_model}
    if conn is not None:
        from .database import get_setting
        cfg["key"] = get_setting(conn, "deepseek_api_key", cfg["key"])
        cfg["base_url"] = get_setting(conn, "deepseek_base_url", cfg["base_url"])
        cfg["model"] = get_setting(conn, "deepseek_model", cfg["model"])
    return cfg


def _image_data_url(image_path: str | Path) -> str:
    """Receipt as a JPEG data URL (max 2000 px) for DeepSeek vision."""
    import base64
    import io

    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(image_path))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((2000, 2000))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _json_from(content: str) -> dict | None:
    try:
        data = json.loads(content)
    except ValueError:
        m = re.search(r"\{.*\}", content or "", re.S)  # model wrapped the JSON in prose
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except ValueError:
            return None
    return data if isinstance(data, dict) else None


def ai_parse(text: str, cfg: dict, image_path: str | Path | None = None) -> dict | None:
    """Ask DeepSeek to read the receipt: the image itself (deepseek-flash reads
    images) plus the Tesseract text. None if not configured or on error."""
    if not cfg.get("key") or not (text.strip() or image_path):
        return None
    import httpx

    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    user: list[dict] = [{"type": "text", "text":
                         "Read this payment receipt. OCR text (may be wrong or empty):\n"
                         + (text[:6000] or "(none)")}]
    if image_path:
        try:
            user.append({"type": "image_url",
                         "image_url": {"url": _image_data_url(image_path), "detail": "high"}})
        except Exception as exc:  # noqa: BLE001
            log.warning("receipt image not attached: %s", exc)
    body = {
        "model": cfg.get("model") or "deepseek-flash",
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": _AI_PROMPT},
                     {"role": "user", "content": user}],
    }
    headers = {"Authorization": f"Bearer {cfg['key']}"}
    try:
        r = httpx.post(url, json=body, timeout=settings.deepseek_timeout, headers=headers)
        if r.status_code == 400:  # e.g. JSON mode not accepted with images: ask plainly
            body.pop("response_format", None)
            r = httpx.post(url, json=body, timeout=settings.deepseek_timeout, headers=headers)
        r.raise_for_status()
        data = _json_from(r.json()["choices"][0]["message"]["content"])
        if data is not None:
            data["_vision"] = len(user) > 1
        return data
    except Exception as exc:  # noqa: BLE001 - AI is a helper, never fatal
        log.warning("deepseek parse failed: %s", exc)
        return None


def _amount_in_text(amount_sen: int, text: str) -> bool:
    """Guard against an AI-invented amount: the figure must appear in the OCR text."""
    whole, cents = divmod(amount_sen, 100)
    flat = text.replace(" ", "")
    forms = {f"{whole}.{cents:02d}", f"{whole:,}.{cents:02d}"}
    return any(f in flat for f in forms)


def merge_ai(parsed: dict, ai: dict | None) -> dict:
    """Combine regex fields with DeepSeek's reading. Adds is_receipt / txn_status / ai_note."""
    out = dict(parsed)
    out.update({"is_receipt": True, "txn_status": "unknown", "ai_note": "", "ai_used": False,
                "amount_verified": True})
    if not ai:
        return out
    out["ai_used"] = True
    out["is_receipt"] = bool(ai.get("is_receipt", True))
    out["txn_status"] = str(ai.get("status") or "unknown").lower()
    out["ai_note"] = str(ai.get("note") or "")[:300]
    amt = ai.get("amount")
    if amt not in (None, ""):
        try:
            sen = round(float(str(amt).replace(",", "").replace("RM", "").strip()) * 100)
        except ValueError:
            sen = 0
        if sen > 0:
            seen = _amount_in_text(sen, parsed.get("raw", ""))
            if seen:
                out["amount_sen"] = sen
            elif ai.get("_vision"):
                # read from the image only: keep it for the admin, never auto-approve on it
                out["amount_sen"] = sen
                out["amount_verified"] = False
    for src, dst in (("reference", "receipt_no"), ("date", "receipt_date"),
                     ("time", "receipt_time"), ("bank", "bank")):
        val = str(ai.get(src) or "").strip()
        if val:
            out[dst] = val.upper()[:40] if dst == "receipt_no" else val[:40]
    out["recipient"] = str(ai.get("recipient") or "")[:80]
    return out


def run_ocr(image_path: str, ai_cfg: dict | None = None) -> dict:
    """Read a receipt: Tesseract text + DeepSeek (image and text). ok=False if
    neither found anything."""
    if not settings.ocr_enabled:
        return {"ok": False, "reason": "disabled", "engine": ""}
    cfg = ai_cfg or ai_config()
    try:
        text, engine = extract_text(image_path)
    except Exception as exc:  # noqa: BLE001 - OCR must never crash the request
        text, engine = "", ""
        log.warning("tesseract failed: %s", exc)
        if not cfg.get("key"):
            return {"ok": False, "reason": f"{type(exc).__name__}: {exc}", "engine": ""}
    ai = ai_parse(text, cfg, image_path)
    parsed = merge_ai(parse_text(text), ai)
    parts = [engine] if engine else []
    if parsed["ai_used"]:
        parts.append("deepseek-vision" if ai.get("_vision") else "deepseek")
    parsed["engine"] = "+".join(parts)
    parsed["ok"] = bool(text.strip()) or bool(parsed.get("amount_sen"))
    if not parsed["ok"]:
        parsed["reason"] = "no text found"
    return parsed
