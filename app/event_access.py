"""Per-event gallery password + secret direct link (rafi, 2026-11-09).

- An event with a password locks the whole gallery: page, thumbnails, previews and
  adding to the cart. Without a password the gallery is open as before.
- The right password (or the secret direct link /e/<slug>?k=<access_key>) sets a
  signed cookie for that event, kept 30 days.
- The cookie is an HMAC of the event id + password + access key, so changing the
  password or pressing "Tukar link" (new key) makes every earlier cookie and the
  old direct link stop working.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from .config import settings

COOKIE_PREFIX = "js_ev_"
MAX_AGE = 30 * 86400
MAX_FAILS = 10            # wrong passwords per IP + event ...
FAIL_WINDOW = 15 * 60     # ... within this many seconds
_fails: dict[tuple[str, int], list[float]] = {}


def is_locked(event) -> bool:
    return bool((event["access_password"] or "").strip())


def new_key() -> str:
    return secrets.token_urlsafe(12)


def _token(event) -> str:
    msg = f"{event['id']}:{event['access_password']}:{event['access_key']}".encode()
    return hmac.new(settings.secret_key.encode(), msg, hashlib.sha256).hexdigest()[:40]


def has_access(request, event) -> bool:
    if not is_locked(event):
        return True
    got = request.cookies.get(f"{COOKIE_PREFIX}{event['id']}", "")
    return bool(got) and hmac.compare_digest(got, _token(event))


def grant(response, event) -> None:
    response.set_cookie(f"{COOKIE_PREFIX}{event['id']}", _token(event), max_age=MAX_AGE,
                        httponly=True, samesite="lax", secure=not settings.is_dev)


def password_ok(event, given: str) -> bool:
    want = (event["access_password"] or "").strip()
    return bool(want) and hmac.compare_digest((given or "").strip().encode(), want.encode())


def key_ok(event, given: str) -> bool:
    want = event["access_key"] or ""
    return bool(want and given) and hmac.compare_digest(given.encode(), want.encode())


def client_ip(request) -> str:
    return (request.headers.get("cf-connecting-ip")
            or (request.client.host if request.client else "") or "?")


def too_many_fails(ip: str, event_id: int) -> bool:
    now = time.time()
    hits = [t for t in _fails.get((ip, event_id), []) if now - t < FAIL_WINDOW]
    _fails[(ip, event_id)] = hits
    return len(hits) >= MAX_FAILS


def record_fail(ip: str, event_id: int) -> None:
    _fails.setdefault((ip, event_id), []).append(time.time())


def direct_url(base: str, event) -> str:
    """Link that opens the gallery without the password."""
    return f"{base}/e/{event['slug']}?k={event['access_key']}" if event["access_key"] else ""


def qr_svg(text: str) -> str:
    """QR code of `text` as an inline SVG string."""
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2)
    out = img.to_string()
    return out.decode() if isinstance(out, bytes) else out
