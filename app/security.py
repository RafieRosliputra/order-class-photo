"""Login codes (two 2-digit numbers), signed-cookie sessions, and lockout."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import settings
from .database import one

SESSION_COOKIE = "js_session"
_serializer = URLSafeTimedSerializer(settings.secret_key, salt="js-session")


def now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _parse(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


# --- login code ----------------------------------------------------------
def generate_code() -> str:
    """Two 2-digit numbers, e.g. '21 88' (easy to type, not high-security)."""
    return f"{secrets.randbelow(90) + 10} {secrets.randbelow(90) + 10}"


def start_login(conn, email: str) -> tuple[bool, str, int]:
    """Create/refresh a login code. Returns (ok, message_key, wait_seconds)."""
    email = email.strip().lower()
    row = one(conn, "SELECT * FROM login_codes WHERE email=?", (email,))
    n = now()

    if row and row["locked_until"]:
        locked = _parse(row["locked_until"])
        if locked and locked > n:
            return False, "locked", int((locked - n).total_seconds())

    if row:
        sent = _parse(row["sent_at"])
        if sent:
            elapsed = (n - sent).total_seconds()
            if elapsed < settings.login_resend_seconds:
                return False, "too_soon", int(settings.login_resend_seconds - elapsed)

    code = generate_code()
    expires = _iso(n + timedelta(seconds=settings.login_code_ttl_seconds))
    conn.execute(
        """INSERT INTO login_codes(email, code, expires_at, sent_at, attempts, locked_until)
           VALUES (?,?,?,?,0,NULL)
           ON CONFLICT(email) DO UPDATE SET
             code=excluded.code, expires_at=excluded.expires_at,
             sent_at=excluded.sent_at, attempts=0, locked_until=NULL""",
        (email, code, expires, _iso(n)),
    )
    return True, code, 0


def verify_code(conn, email: str, code: str) -> tuple[bool, str]:
    """Check a submitted code. Returns (ok, message_key)."""
    email = email.strip().lower()
    code = " ".join(code.split())  # normalise whitespace
    row = one(conn, "SELECT * FROM login_codes WHERE email=?", (email,))
    n = now()
    if not row:
        return False, "no_code"

    if row["locked_until"]:
        locked = _parse(row["locked_until"])
        if locked and locked > n:
            return False, "locked"

    if _parse(row["expires_at"]) and _parse(row["expires_at"]) < n:
        return False, "expired"

    if code == row["code"]:
        conn.execute("DELETE FROM login_codes WHERE email=?", (email,))
        return True, "ok"

    attempts = row["attempts"] + 1
    if attempts >= settings.login_max_attempts:
        locked_until = _iso(n + timedelta(minutes=settings.login_lock_minutes))
        conn.execute(
            "UPDATE login_codes SET attempts=?, locked_until=? WHERE email=?",
            (attempts, locked_until, email),
        )
        return False, "locked"
    conn.execute("UPDATE login_codes SET attempts=? WHERE email=?", (attempts, email))
    return False, "wrong"


# --- sessions --------------------------------------------------------------
def issue_session(customer_id: int) -> str:
    return _serializer.dumps({"cid": customer_id})


def read_session(token: str | None) -> int | None:
    if not token:
        return None
    try:
        data = _serializer.loads(token, max_age=settings.session_days * 86400)
        return int(data["cid"])
    except (BadSignature, SignatureExpired, KeyError, ValueError, TypeError):
        return None
