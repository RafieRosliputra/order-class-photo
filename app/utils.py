"""Small shared helpers: money, order numbers, slugs, WhatsApp links."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from .config import settings
from .database import one

TZ = ZoneInfo(settings.timezone)


def local_now() -> datetime:
    return datetime.now(TZ)


# --- money (stored in sen) -------------------------------------------------
def to_sen(ringgit: float | str) -> int:
    return round(float(ringgit) * 100)


def rm(sen: int | None) -> str:
    if sen is None:
        sen = 0
    return f"RM{sen / 100:,.2f}"


# --- slugs -----------------------------------------------------------------
def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "event"


def unique_slug(conn, base: str) -> str:
    base = slugify(base)
    slug, i = base, 2
    while one(conn, "SELECT 1 FROM events WHERE slug=?", (slug,)):
        slug = f"{base}-{i}"
        i += 1
    return slug


# --- order numbers: YYYYMMDD-NNN -------------------------------------------
def next_order_no(conn) -> str:
    prefix = local_now().strftime("%Y%m%d")
    row = one(
        conn,
        "SELECT COUNT(*) AS c FROM orders WHERE order_no LIKE ?",
        (f"{prefix}-%",),
    )
    seq = (row["c"] if row else 0) + 1
    return f"{prefix}-{seq:03d}"


# --- school / class parsing ------------------------------------------------
def split_school_class(folder_name: str, delimiter: str) -> tuple[str, str]:
    """'SKA - 3 Bestari' -> ('SKA', '3 Bestari'); no delimiter -> ('', folder)."""
    delimiter = delimiter or " - "
    if delimiter in folder_name:
        school, _, cls = folder_name.partition(delimiter)
        return school.strip(), cls.strip()
    return "", folder_name.strip()


# --- WhatsApp link ---------------------------------------------------------
def whatsapp_link(title: str, order_no: str = "", email: str = "", phone: str = "") -> str:
    lines = [f"*{title}*"]
    if order_no:
        lines.append(f"No. Order: {order_no}")
    if email:
        lines.append(f"Email: {email}")
    if phone:
        lines.append(f"Telefon: {phone}")
    text = quote("\n".join(lines))
    return f"https://wa.me/{settings.whatsapp_number}?text={text}"


# --- Google Maps link ------------------------------------------------------
def gmaps_link(lat: float | None, lng: float | None, address: str = "") -> str:
    if lat is not None and lng is not None:
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
    if address:
        return f"https://www.google.com/maps/search/?api=1&query={quote(address)}"
    return ""


STATUS_FLOW = ["awaiting_payment", "reviewing", "paid", "printing", "ready"]
