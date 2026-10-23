"""Order + receipt business logic (kept out of the routers)."""
from __future__ import annotations

import logging
import secrets

from . import imaging, nextcloud, printing, sheets
from .config import settings
from .database import audit, db, one, query
from .email_send import send_payment_confirmed
from .ocr import run_ocr
from .pricing import compute_order_totals, postage_for
from .utils import local_now, next_order_no

log = logging.getLogger("orders")


# --- order creation --------------------------------------------------------
def create_order_from_cart(conn, event_id, customer_id, cart, *, delivery, address,
                           lat, lng, zone, category, phone) -> int:
    order_no = next_order_no(conn)
    postage = postage_for(conn, event_id, delivery, zone)
    order_id = conn.execute(
        """INSERT INTO orders(order_no, event_id, customer_id, status, delivery_method,
               postage_sen, address, lat, lng, category, phone_used)
           VALUES (?,?,?,'awaiting_payment',?,?,?,?,?,?,?)""",
        (order_no, event_id, customer_id, delivery, postage, address, lat, lng, category, phone),
    ).lastrowid

    for key, qty in cart.items():
        parts = key.split(":")
        if len(parts) != 3:
            continue
        _, photo_id, size_id = parts
        photo = one(conn, "SELECT * FROM photos WHERE id=?", (photo_id,))
        size = one(conn, "SELECT * FROM sizes WHERE id=?", (size_id,))
        cls = one(conn, "SELECT * FROM classes WHERE id=?", (photo["class_id"],)) if photo else None
        if not (photo and size):
            continue
        conn.execute(
            """INSERT INTO order_items(order_id, photo_id, size_id, qty, unit_price_sen,
                   filename, rel_path, school, class_name, size_code)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (order_id, photo["id"], size["id"], int(qty), size["price_sen"],
             photo["filename"], photo["rel_path"],
             cls["school"] if cls else "", cls["name"] if cls else "", size["code"]),
        )
    compute_order_totals(conn, order_id)
    audit(conn, f"customer:{customer_id}", "order_created", "order", order_id, order_no)
    return order_id


# --- receipt processing ----------------------------------------------------
def process_receipt(conn, order_id, customer_id, data, filename, mime, forced=False) -> dict:
    """Store + OCR a receipt, update payment state. Returns a result dict."""
    order = one(conn, "SELECT * FROM orders WHERE id=?", (order_id,))
    if not order:
        return {"ok": False, "error": "no_order"}

    stem = f"{order['order_no']}-{secrets.token_hex(4)}"
    stored = imaging.receipt_to_webp(data, mime, stem)
    imaging.trash_original(data, filename, stem)  # original -> trash (auto-cleared)

    ocr = run_ocr(str(stored))
    amount_sen = ocr.get("amount_sen") if ocr.get("ok") else None
    receipt_no = (ocr.get("receipt_no") or "") if ocr.get("ok") else ""
    ocr_status = "ok" if ocr.get("ok") and amount_sen else "failed"

    # duplicate check (system-wide) on receipt number
    duplicate = False
    if receipt_no:
        dup = one(conn, "SELECT 1 FROM receipts WHERE receipt_no=? AND receipt_no!=''", (receipt_no,))
        duplicate = bool(dup)
    if duplicate and not forced:
        # Don't store yet — warn the customer; they may force-submit.
        return {"ok": False, "duplicate": True, "receipt_no": receipt_no}

    accepted = 1 if (ocr_status == "ok" and amount_sen and not duplicate) else 0
    rid = conn.execute(
        """INSERT INTO receipts(order_id, customer_id, orig_filename, stored_path, mime,
               amount_sen, receipt_no, receipt_date, receipt_time, bank, ocr_raw,
               ocr_status, accepted, duplicate, forced)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (order_id, customer_id, filename,
         str(stored.relative_to(settings.data_path)), mime, amount_sen, receipt_no,
         ocr.get("receipt_date", "") if ocr.get("ok") else "",
         ocr.get("receipt_time", "") if ocr.get("ok") else "",
         ocr.get("bank", "") if ocr.get("ok") else "",
         (ocr.get("raw", "") if ocr.get("ok") else ocr.get("reason", ""))[:5000],
         ocr_status, accepted, int(duplicate), int(forced)),
    ).lastrowid

    if duplicate and forced:
        audit(conn, f"customer:{customer_id}", "receipt_duplicate_forced", "order", order_id, receipt_no)
    if ocr_status == "failed":
        audit(conn, "system", "receipt_ocr_failed", "order", order_id, ocr.get("reason", ""))

    state = _reconcile_payment(conn, order_id)
    state.update({"ok": True, "receipt_id": rid, "ocr_status": ocr_status,
                  "accepted": bool(accepted), "duplicate": duplicate})
    return state


def _reconcile_payment(conn, order_id) -> dict:
    """Recompute paid total; auto-mark paid only on an EXACT match."""
    order = one(conn, "SELECT * FROM orders WHERE id=?", (order_id,))
    total = order["total_sen"]
    rows = query(conn, "SELECT amount_sen FROM receipts WHERE order_id=? AND accepted=1", (order_id,))
    paid = sum(int(r["amount_sen"] or 0) for r in rows)

    status = order["status"]
    overpaid = paid > total
    if order["status"] not in ("paid", "printing", "ready", "cancelled"):
        if paid == total:
            status = "paid"
        elif paid > 0:
            status = "reviewing"   # partial or overpaid -> needs attention
    conn.execute(
        "UPDATE orders SET paid_sen=?, status=?, updated_at=datetime('now') WHERE id=?",
        (paid, status, order_id),
    )
    if status == "paid" and order["status"] != "paid":
        audit(conn, "system", "order_paid", "order", order_id, f"{paid}sen")
    return {
        "status": status, "paid_sen": paid, "total_sen": total,
        "balance_sen": max(0, total - paid), "overpaid": overpaid,
        "just_paid": status == "paid" and order["status"] != "paid",
    }


# --- finalisation (run in background after a successful payment) -----------
def finalize_payment(order_id: int) -> None:
    """Copy prints to Nextcloud, append the job-list sheet, email the customer."""
    try:
        with db() as conn:
            order = one(conn, "SELECT * FROM orders WHERE id=?", (order_id,))
            if not order or order["status"] != "paid":
                return
            cust = one(conn, "SELECT * FROM customers WHERE id=?", (order["customer_id"],))
            session_row = sheets.get_or_create_session(conn, order["event_id"])
            conn.execute("UPDATE orders SET print_session_id=? WHERE id=?",
                         (session_row["id"], order_id))
            try:
                printing.copy_order_to_print(conn, order_id)
            except Exception:  # noqa: BLE001
                log.exception("print copy failed for order %s", order_id)
            try:
                sheets.append_order(conn, order_id, session_row)
            except Exception:  # noqa: BLE001
                log.exception("sheet append failed for order %s", order_id)
            status_url = f"{settings.base_url}/order/{order['order_no']}"
            try:
                send_payment_confirmed(cust["email"], order["order_no"], order["total_sen"], status_url)
            except Exception:  # noqa: BLE001
                log.exception("confirmation email failed for order %s", order_id)
    except Exception:  # noqa: BLE001
        log.exception("finalize_payment failed for order %s", order_id)
