"""Google Sheets job list (one sheet per print session).

A *print session* starts when the first order is paid after the print folder was
empty; it maps to one Google Sheet. Clearing the print folder (admin) ends the
session, so the next paid order opens a fresh sheet.

Columns (one row per photo+size): order no, date, name, phone, school, class,
filename, size, copies, delivery, payment status, amount (RM).
"""
from __future__ import annotations

from .config import settings
from .database import one, query
from .utils import local_now, rm

HEADER = [
    "No. Order", "Tarikh", "Nama", "Telefon", "Sekolah", "Kelas",
    "Nama Fail", "Saiz", "Salinan", "Hantar", "Status Bayar", "Jumlah (RM)",
]

_gc = None


def is_configured() -> bool:
    return bool(settings.google_sa_json and settings.gsheet_parent_folder_id)


def _client():
    global _gc
    if _gc is None:
        import gspread
        _gc = gspread.service_account(filename=settings.google_sa_json)
    return _gc


def get_or_create_session(conn, event_id: int):
    """Return the active print-session row for an event, creating a sheet if needed."""
    row = one(conn, "SELECT * FROM print_sessions WHERE event_id=? AND active=1", (event_id,))
    if row:
        return row
    ev = one(conn, "SELECT * FROM events WHERE id=?", (event_id,))
    sheet_id, url = "", ""
    if is_configured():
        gc = _client()
        title = f"{ev['name']} — {local_now():%Y-%m-%d %H%M}"
        sh = gc.create(title, folder_id=settings.gsheet_parent_folder_id)
        ws = sh.sheet1
        ws.update(range_name="A1", values=[HEADER])
        ws.freeze(rows=1)
        sheet_id, url = sh.id, sh.url
    sid = conn.execute(
        "INSERT INTO print_sessions(event_id, sheet_id, sheet_url, active) VALUES (?,?,?,1)",
        (event_id, sheet_id, url),
    ).lastrowid
    return one(conn, "SELECT * FROM print_sessions WHERE id=?", (sid,))


def end_session(conn, event_id: int) -> None:
    conn.execute("UPDATE print_sessions SET active=0 WHERE event_id=? AND active=1", (event_id,))


def append_order(conn, order_id: int, session_row) -> None:
    """Append one row per order item to the session's sheet."""
    if not session_row or not session_row["sheet_id"] or not is_configured():
        return
    order = one(conn, "SELECT * FROM orders WHERE id=?", (order_id,))
    cust = one(conn, "SELECT * FROM customers WHERE id=?", (order["customer_id"],))
    items = query(conn, "SELECT * FROM order_items WHERE order_id=?", (order_id,))
    delivery = "Pos" if order["delivery_method"] == "post" else "Pickup"
    rows = [[
        order["order_no"], order["created_at"], cust["name"], order["phone_used"] or cust["phone"],
        it["school"], it["class_name"], it["filename"], it["size_code"], it["qty"],
        delivery, "LUNAS", rm(it["qty"] * it["unit_price_sen"]).replace("RM", ""),
    ] for it in items]

    gc = _client()
    sh = gc.open_by_key(session_row["sheet_id"])
    sh.sheet1.append_rows(rows, value_input_option="USER_ENTERED")
