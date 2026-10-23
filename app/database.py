"""SQLite access (no ORM) + schema bootstrap.

Money is stored in **sen** (integers). Format to RM only at display time.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from .config import settings

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    event_date      TEXT,
    nextcloud_folder TEXT NOT NULL DEFAULT '',
    nextcloud_id    TEXT NOT NULL DEFAULT '',       -- which Nextcloud instance
    class_delimiter TEXT NOT NULL DEFAULT ' - ',   -- "SEKOLAH - KELAS"
    close_date      TEXT,                           -- ISO date; past = closed
    status          TEXT NOT NULL DEFAULT 'open',   -- open | closed
    pickup_location TEXT NOT NULL DEFAULT '',
    pay_qrpay_image TEXT NOT NULL DEFAULT '',
    pay_bank_no     TEXT NOT NULL DEFAULT '',
    postage_west_sen INTEGER NOT NULL DEFAULT 1000,
    postage_east_sen INTEGER NOT NULL DEFAULT 1800,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sizes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id  INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    code      TEXT NOT NULL,            -- 4R, 6R, 8R, 11R
    label     TEXT NOT NULL,            -- 4x6"
    price_sen INTEGER NOT NULL,
    sort      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS classes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    school     TEXT NOT NULL DEFAULT '',  -- parsed from folder name, before delimiter
    name       TEXT NOT NULL,             -- class, after delimiter (or whole folder)
    folder_path TEXT NOT NULL,            -- WebDAV path relative to event folder
    sort       INTEGER NOT NULL DEFAULT 0,
    UNIQUE(event_id, folder_path)
);

CREATE TABLE IF NOT EXISTS photos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    class_id    INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    filename    TEXT NOT NULL,            -- original filename, kept for print
    rel_path    TEXT NOT NULL,            -- full WebDAV path to the original
    etag        TEXT NOT NULL DEFAULT '',
    preview_path TEXT NOT NULL DEFAULT '',-- local cached WebP (large preview)
    thumb_path  TEXT NOT NULL DEFAULT '', -- local cached WebP (grid thumb)
    width       INTEGER NOT NULL DEFAULT 0,
    height      INTEGER NOT NULL DEFAULT 0,
    sort        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(event_id, rel_path)
);

CREATE TABLE IF NOT EXISTS customers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT UNIQUE NOT NULL,
    name       TEXT NOT NULL DEFAULT '',
    phone      TEXT NOT NULL DEFAULT '',   -- current default
    phone_history TEXT NOT NULL DEFAULT '[]', -- JSON list of {phone, at}
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_login TEXT
);

CREATE TABLE IF NOT EXISTS login_codes (
    email       TEXT PRIMARY KEY,
    code        TEXT NOT NULL,            -- "21 88"
    expires_at  TEXT NOT NULL,
    sent_at     TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no      TEXT UNIQUE NOT NULL,     -- YYYYMMDD-NNN
    event_id      INTEGER NOT NULL REFERENCES events(id),
    customer_id   INTEGER NOT NULL REFERENCES customers(id),
    status        TEXT NOT NULL DEFAULT 'awaiting_payment',
    -- awaiting_payment | reviewing | paid | printing | ready | cancelled
    delivery_method TEXT NOT NULL DEFAULT 'pickup',  -- pickup | post
    postage_sen   INTEGER NOT NULL DEFAULT 0,
    address       TEXT NOT NULL DEFAULT '',
    lat           REAL,
    lng           REAL,
    category      TEXT NOT NULL DEFAULT '',
    phone_used    TEXT NOT NULL DEFAULT '',
    subtotal_sen  INTEGER NOT NULL DEFAULT 0,
    total_sen     INTEGER NOT NULL DEFAULT 0,
    paid_sen      INTEGER NOT NULL DEFAULT 0,  -- sum of accepted receipts
    cancel_reason TEXT NOT NULL DEFAULT '',
    print_session_id INTEGER,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS order_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    photo_id     INTEGER NOT NULL REFERENCES photos(id),
    size_id      INTEGER NOT NULL REFERENCES sizes(id),
    qty          INTEGER NOT NULL DEFAULT 1,
    unit_price_sen INTEGER NOT NULL,
    -- snapshot so the job list survives even if source photo is re-imported
    filename     TEXT NOT NULL DEFAULT '',
    rel_path     TEXT NOT NULL DEFAULT '',
    school       TEXT NOT NULL DEFAULT '',
    class_name   TEXT NOT NULL DEFAULT '',
    size_code    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS receipts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    orig_filename TEXT NOT NULL DEFAULT '',
    stored_path TEXT NOT NULL DEFAULT '',   -- local WebP (compressed)
    mime        TEXT NOT NULL DEFAULT '',
    amount_sen  INTEGER,
    receipt_no  TEXT NOT NULL DEFAULT '',
    receipt_date TEXT NOT NULL DEFAULT '',
    receipt_time TEXT NOT NULL DEFAULT '',
    bank        TEXT NOT NULL DEFAULT '',
    ocr_raw     TEXT NOT NULL DEFAULT '',
    ocr_status  TEXT NOT NULL DEFAULT 'pending', -- pending | ok | failed | manual
    accepted    INTEGER NOT NULL DEFAULT 0,      -- counted toward paid_sen
    duplicate   INTEGER NOT NULL DEFAULT 0,
    forced      INTEGER NOT NULL DEFAULT 0,      -- customer forced a duplicate submit
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS print_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    sheet_id   TEXT NOT NULL DEFAULT '',
    sheet_url  TEXT NOT NULL DEFAULT '',
    active     INTEGER NOT NULL DEFAULT 1,
    started_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL DEFAULT (datetime('now')),
    actor     TEXT NOT NULL DEFAULT 'system',
    action    TEXT NOT NULL,
    entity    TEXT NOT NULL DEFAULT '',
    entity_id TEXT NOT NULL DEFAULT '',
    detail    TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_photos_class ON photos(class_id);
CREATE INDEX IF NOT EXISTS idx_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_receipts_order ON receipts(order_id);
CREATE INDEX IF NOT EXISTS idx_receipts_no ON receipts(receipt_no);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_classes_event ON classes(event_id);
"""


def _connect() -> sqlite3.Connection:
    Path(settings.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.sqlite_path, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db():
    """Short-lived connection per unit of work."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    settings.ensure_dirs()
    conn = _connect()
    try:
        conn.executescript(SCHEMA)
        # lightweight migrations for existing databases
        for stmt in (
            "ALTER TABLE events ADD COLUMN nextcloud_id TEXT NOT NULL DEFAULT ''",
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()
    finally:
        conn.close()


# --- tiny helpers ---------------------------------------------------------
def query(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, tuple(params)).fetchall()


def one(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    return conn.execute(sql, tuple(params)).fetchone()


def execute(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> int:
    cur = conn.execute(sql, tuple(params))
    return cur.lastrowid


def audit(conn: sqlite3.Connection, actor: str, action: str,
          entity: str = "", entity_id: Any = "", detail: str = "") -> None:
    conn.execute(
        "INSERT INTO audit_log(actor, action, entity, entity_id, detail) VALUES (?,?,?,?,?)",
        (actor, action, entity, str(entity_id), detail),
    )
