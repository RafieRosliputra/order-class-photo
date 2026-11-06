"""Order + receipt business logic (kept out of the routers)."""
from __future__ import annotations

import logging
import secrets
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from . import imaging, nextcloud, printing, sheets
from .config import settings
from .database import audit, db, get_setting, one, query
from .email_send import send_admin_notice, send_payment_confirmed
from .ocr import ai_config, run_ocr
from .pricing import compute_order_totals, postage_for
from .utils import local_now, next_order_no

log = logging.getLogger("orders")


# --- order creation --------------------------------------------------------
def create_order_from_cart(conn, event_id, customer_id, cart, *, delivery, address,
                           lat, lng, zone, category, phone, pickup_location="") -> int:
    order_no = next_order_no(conn)
    postage = postage_for(conn, event_id, delivery, zone)
    order_id = conn.execute(
        """INSERT INTO orders(order_no, event_id, customer_id, status, delivery_method,
               postage_sen, address, lat, lng, category, phone_used, pickup_location)
           VALUES (?,?,?,'awaiting_payment',?,?,?,?,?,?,?,?)""",
        (order_no, event_id, customer_id, delivery, postage, address, lat, lng, category, phone,
         pickup_location if delivery == "pickup" else ""),
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
# ocr_note codes (shown to customer + admin, labels in i18n "ocr_note_<code>")
NOTE_MATCH, NOTE_PARTIAL, NOTE_OVER = "match", "partial", "over"
NOTE_UNREADABLE, NOTE_NO_AMOUNT, NOTE_NOT_RECEIPT = "unreadable", "no_amount", "not_receipt"
NOTE_FAILED_TXN, NOTE_DUPLICATE, NOTE_OLD_DATE = "failed_txn", "duplicate", "old_date"


def _ocr_bytes(conn, data: bytes, mime: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            src = imaging.ocr_source(data, mime, Path(tmp))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": f"image: {exc}", "engine": ""}
        return run_ocr(str(src), ai_config(conn))


def _judge(conn, order, ocr: dict, receipt_id: int | None) -> tuple[int, str, bool]:
    """Decide (accepted, note, duplicate). Only a clean reading counts toward paid."""
    if not ocr.get("ok"):
        return 0, NOTE_UNREADABLE, False
    if not ocr.get("is_receipt", True):
        return 0, NOTE_NOT_RECEIPT, False
    if ocr.get("txn_status") in ("failed", "pending"):
        return 0, NOTE_FAILED_TXN, False
    amount = ocr.get("amount_sen")
    if not amount:
        return 0, NOTE_NO_AMOUNT, False
    # same receipt uploaded twice (identical OCR text) counts once
    raw = (ocr.get("raw") or "").strip()
    if raw and one(conn, "SELECT 1 FROM receipts WHERE order_id=? AND id!=? AND accepted=1 "
                   "AND (ocr_raw=? OR ocr_raw LIKE ?)",
                   (order["id"], receipt_id or 0, raw, "%\n\n" + raw)):
        return 0, NOTE_DUPLICATE, True
    ref = ocr.get("receipt_no") or ""
    if ref:
        dup = one(conn, "SELECT 1 FROM receipts WHERE receipt_no=? AND receipt_no!='' AND id!=?",
                  (ref, receipt_id or 0))
        if dup:
            return 0, NOTE_DUPLICATE, True
    rdate = ocr.get("receipt_date") or ""
    if rdate and (order["created_at"] or "")[:10]:
        try:
            made = datetime.strptime(order["created_at"][:10], "%Y-%m-%d").date()
            if datetime.strptime(rdate, "%Y-%m-%d").date() < made - timedelta(days=1):
                return 0, NOTE_OLD_DATE, False
        except ValueError:
            pass
    already = one(conn, "SELECT COALESCE(SUM(amount_sen),0) s FROM receipts WHERE order_id=? "
                  "AND accepted=1 AND id!=?", (order["id"], receipt_id or 0))["s"]
    due = order["total_sen"] - already
    if amount == due:
        return 1, NOTE_MATCH, False
    return 1, (NOTE_PARTIAL if amount < due else NOTE_OVER), False


def _store_ocr(conn, receipt_id: int, ocr: dict, accepted: int, note: str, duplicate: bool) -> None:
    ok = bool(ocr.get("ok"))
    raw = ocr.get("raw", "") if ok else ocr.get("reason", "")
    if ocr.get("ai_note"):
        raw = f"[AI] {ocr['ai_note']}\n\n{raw}"
    conn.execute(
        """UPDATE receipts SET amount_sen=?, receipt_no=?, receipt_date=?, receipt_time=?,
               bank=?, ocr_raw=?, ocr_status=?, accepted=?, duplicate=?, ocr_note=?,
               ocr_engine=?, ocr_checked_at=datetime('now') WHERE id=?""",
        (ocr.get("amount_sen") if ok else None, (ocr.get("receipt_no") or "") if ok else "",
         ocr.get("receipt_date", "") if ok else "", ocr.get("receipt_time", "") if ok else "",
         ocr.get("bank", "") if ok else "", raw[:5000],
         "ok" if ok and ocr.get("amount_sen") else "failed", accepted, int(duplicate),
         note, ocr.get("engine", ""), receipt_id),
    )


def process_receipt(conn, order_id, customer_id, data, filename, mime, forced=False) -> dict:
    """Store + OCR a receipt, update payment state. Returns a result dict."""
    order = one(conn, "SELECT * FROM orders WHERE id=? AND deleted_at IS NULL", (order_id,))
    if not order:
        return {"ok": False, "error": "no_order"}

    ocr = _ocr_bytes(conn, data, mime)
    receipt_no = (ocr.get("receipt_no") or "") if ocr.get("ok") else ""
    if receipt_no and not forced and one(
            conn, "SELECT 1 FROM receipts WHERE receipt_no=? AND receipt_no!=''", (receipt_no,)):
        # Don't store yet — warn the customer; they may force-submit.
        return {"ok": False, "duplicate": True, "receipt_no": receipt_no}

    stem = f"{order['order_no']}-{secrets.token_hex(4)}"
    stored = imaging.receipt_to_webp(data, mime, stem)
    imaging.trash_original(data, filename, stem)  # original -> trash (auto-cleared)
    rid = conn.execute(
        """INSERT INTO receipts(order_id, customer_id, orig_filename, stored_path, mime, forced)
           VALUES (?,?,?,?,?,?)""",
        (order_id, customer_id, filename, str(stored.relative_to(settings.data_path)), mime,
         int(forced)),
    ).lastrowid
    accepted, note, duplicate = _judge(conn, order, ocr, rid)
    _store_ocr(conn, rid, ocr, accepted, note, duplicate)

    if duplicate and forced:
        audit(conn, f"customer:{customer_id}", "receipt_duplicate_forced", "order", order_id, receipt_no)
    audit(conn, "system", "receipt_ocr", "order", order_id,
          f"{note} {ocr.get('engine', '')} {ocr.get('amount_sen')} {ocr.get('reason', '')}".strip())

    state = _reconcile_payment(conn, order_id)
    state.update({"ok": True, "receipt_id": rid, "note": note,
                  "accepted": bool(accepted), "duplicate": duplicate})
    return state


def rerun_receipt(conn, receipt_id: int) -> dict | None:
    """OCR an already-stored receipt again (original from trash if still there)."""
    r = one(conn, "SELECT * FROM receipts WHERE id=?", (receipt_id,))
    if not r:
        return None
    order = one(conn, "SELECT * FROM orders WHERE id=?", (r["order_id"],))
    if not order:
        return None
    stem = Path(r["stored_path"]).stem
    originals = sorted(settings.trash_dir.glob(f"{stem}.*")) if stem else []
    src = originals[0] if originals else settings.data_path / r["stored_path"]
    if not src.exists():
        return None
    data = src.read_bytes()
    mime = "application/pdf" if data[:5] == b"%PDF-" else "image/png"
    ocr = _ocr_bytes(conn, data, mime)
    accepted, note, duplicate = _judge(conn, order, ocr, receipt_id)
    _store_ocr(conn, receipt_id, ocr, accepted, note, duplicate)
    audit(conn, "system", "receipt_ocr_rerun", "order", order["id"],
          f"{note} {ocr.get('engine', '')} {ocr.get('amount_sen')}".strip())
    state = _reconcile_payment(conn, order["id"])
    state.update({"note": note, "order_id": order["id"]})
    return state


def pending_receipt_ids(conn, only_unchecked: bool = False) -> list[int]:
    """Receipts not verified on orders still waiting (the 'stuck' ones).
    only_unchecked: skip ones the current OCR already looked at (for the timer)."""
    extra = "AND r.ocr_checked_at IS NULL" if only_unchecked else ""
    rows = query(conn, f"""SELECT r.id FROM receipts r JOIN orders o ON o.id=r.order_id
                          WHERE o.deleted_at IS NULL AND o.status IN ('awaiting_payment','reviewing')
                            AND r.accepted=0 AND r.duplicate=0
                            AND r.ocr_status IN ('failed','pending') {extra}
                          ORDER BY r.id""")
    return [r["id"] for r in rows]


def rescan_pending(only_unchecked: bool = True) -> int:
    """Re-OCR stuck receipts; finalise + notify where an order becomes paid."""
    with db() as conn:
        ids = pending_receipt_ids(conn, only_unchecked)
    done = 0
    for rid in ids:
        try:
            with db() as conn:
                state = rerun_receipt(conn, rid)
            if state:
                done += 1
                after_receipt(state["order_id"], state)
        except Exception:  # noqa: BLE001
            log.exception("rescan failed for receipt %s", rid)
    log.info("rescan: %s/%s receipts re-checked", done, len(ids))
    return done


def after_receipt(order_id: int, state: dict) -> None:
    """Background follow-up of an OCR result: print/sheet/customer email, admin email."""
    if state.get("just_paid"):
        finalize_payment(order_id)
        notify_admin(order_id, "paid")
    elif state.get("status") == "reviewing":
        notify_admin(order_id, "review")


def notify_admin(order_id: int, kind: str) -> None:
    """Email the admin (Rafi) that an order is paid or needs a receipt check."""
    try:
        with db() as conn:
            to = get_setting(conn, "admin_notify_email", settings.admin_notify_email)
            o = one(conn, """SELECT o.*, e.name event_name, c.email cust_email, c.name cust_name
                             FROM orders o JOIN events e ON e.id=o.event_id
                             JOIN customers c ON c.id=o.customer_id WHERE o.id=?""", (order_id,))
            r = one(conn, "SELECT * FROM receipts WHERE order_id=? ORDER BY id DESC LIMIT 1", (order_id,))
        if not (to and o):
            return
        send_admin_notice(to, kind, o, r, f"{settings.base_url}/admin/orders/{order_id}")
    except Exception:  # noqa: BLE001
        log.exception("admin notice failed for order %s", order_id)


def _reconcile_payment(conn, order_id) -> dict:
    """Recompute paid total; auto-mark paid only on an EXACT match.
    Any receipt that is not an exact match moves the order to 'reviewing'."""
    order = one(conn, "SELECT * FROM orders WHERE id=?", (order_id,))
    total = order["total_sen"]
    rows = query(conn, "SELECT amount_sen FROM receipts WHERE order_id=? AND accepted=1", (order_id,))
    paid = sum(int(r["amount_sen"] or 0) for r in rows)
    has_receipt = bool(one(conn, "SELECT 1 FROM receipts WHERE order_id=?", (order_id,)))

    status = order["status"]
    overpaid = paid > total
    if order["status"] not in ("paid", "printing", "ready", "cancelled"):
        if paid == total and paid > 0:
            status = "paid"
        elif paid > 0 or has_receipt:
            status = "reviewing"   # partial, overpaid or unreadable -> needs attention
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
