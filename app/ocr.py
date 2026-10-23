"""Receipt OCR (PaddleOCR) + regex field extraction.

`parse_text()` is pure (no PaddleOCR) so it is unit-testable. `run_ocr()` lazily
loads PaddleOCR; if OCR is disabled or unavailable, callers flag the receipt for
manual admin review.
"""
from __future__ import annotations

import re
from datetime import datetime

from .config import settings

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
    r"(?:ref(?:erence)?(?:\s*(?:no|id|number))?|transaction\s*(?:id|no)|"
    r"no\.?\s*rujukan|resit|receipt(?:\s*no)?)\s*[:#]?\s*([A-Za-z0-9\-]{6,30})",
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


def _engine():
    global _paddle
    if _paddle is None:
        from paddleocr import PaddleOCR
        _paddle = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    return _paddle


def run_ocr(image_path: str) -> dict:
    """OCR an image file and parse it. Returns parsed dict; ok=False if unavailable."""
    if not settings.ocr_enabled:
        return {"ok": False, "reason": "disabled"}
    try:
        ocr = _engine()
        res = ocr.ocr(image_path, cls=True)
        lines = []
        for page in res or []:
            for line in page or []:
                try:
                    lines.append(line[1][0])
                except (IndexError, TypeError):
                    continue
        text = "\n".join(lines)
        parsed = parse_text(text)
        parsed["ok"] = True
        return parsed
    except Exception as exc:  # noqa: BLE001 - OCR must never crash the request
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}
