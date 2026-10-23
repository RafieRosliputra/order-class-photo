"""Generate a dynamic DuitNow QR (Malaysia National QR / EMVCo MPM) from the
merchant's STATIC QR payload, with the order amount and a reference embedded.

How it works: a DuitNow QR is an EMVCo Merchant-Presented-Mode TLV string. We
parse the static payload, switch Point-of-Initiation 11 (static) → 12 (dynamic),
set Tag 54 (amount), set a reference inside Tag 62 (Additional Data), and
recompute the Tag 63 CRC-16. The account stays the merchant's own.

IMPORTANT: this only pre-fills the payer's app. It does NOT confirm payment —
confirmation still comes from the uploaded-receipt OCR flow. Test with a few
banks / e-wallets before relying on it.

Provide the static payload (decoded once from the printed static QR) in
settings.duitnow_static_payload.
"""
from __future__ import annotations

import io

from .config import settings

TAG_POI = "01"          # Point of Initiation Method: 11 static / 12 dynamic
TAG_AMOUNT = "54"       # Transaction Amount
TAG_ADDITIONAL = "62"   # Additional Data Field Template (nested)
TAG_CRC = "63"          # CRC


def crc16(data: str) -> str:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF), uppercase hex."""
    crc = 0xFFFF
    for b in data.encode("ascii"):
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def parse_tlv(payload: str) -> list[tuple[str, str]]:
    """Parse one level of EMVCo TLV into ordered (tag, value) pairs."""
    out, i, n = [], 0, len(payload)
    while i + 4 <= n:
        tag = payload[i:i + 2]
        length = int(payload[i + 2:i + 4])
        val = payload[i + 4:i + 4 + length]
        out.append((tag, val))
        i += 4 + length
    return out


def _tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def build_dynamic(static_payload: str, amount_sen: int, reference: str = "",
                  ref_subtag: str = "05") -> str:
    """Return a dynamic DuitNow payload with amount + reference embedded."""
    fields = dict(parse_tlv(static_payload))
    fields[TAG_POI] = "12"                                   # -> dynamic
    fields[TAG_AMOUNT] = f"{amount_sen / 100:.2f}"           # e.g. 40.00

    if reference:
        sub = dict(parse_tlv(fields.get(TAG_ADDITIONAL, "")))
        sub[ref_subtag] = reference[:25]                     # EMV limit
        fields[TAG_ADDITIONAL] = "".join(_tlv(t, sub[t]) for t in sorted(sub))

    fields.pop(TAG_CRC, None)
    body = "".join(_tlv(t, fields[t]) for t in sorted(fields, key=lambda x: int(x)))
    body += TAG_CRC + "04"                                   # CRC tag + length
    return body + crc16(body)


def make_qr_png(payload: str) -> bytes:
    import qrcode
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def is_configured() -> bool:
    return bool(settings.duitnow_enabled and settings.duitnow_static_payload)


def qr_for_order_png(amount_sen: int, phone: str) -> bytes:
    ref = "".join(ch for ch in (phone or "") if ch.isdigit())
    payload = build_dynamic(settings.duitnow_static_payload, amount_sen, ref,
                            settings.duitnow_ref_subtag)
    return make_qr_png(payload)
