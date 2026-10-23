"""Admin panel. Mounted under /admin and protected by Cloudflare Access
(no application-level auth). The authenticated email (from the CF header) is
used only for the audit log.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import RedirectResponse

from .. import imaging, nextcloud, sheets, backup, printing
from ..config import settings
from ..database import audit, db, one, query
from ..deps import render
from ..pricing import compute_order_totals
from ..utils import rm, slugify, split_school_class, to_sen, unique_slug

log = logging.getLogger("admin")
router = APIRouter(prefix="/admin")


def admin_email(request: Request) -> str:
    return request.headers.get(settings.admin_email_header, "admin@local")


# --- dashboard -------------------------------------------------------------
@router.get("")
@router.get("/")
def dashboard(request: Request):
    with db() as conn:
        events = query(conn, "SELECT * FROM events ORDER BY created_at DESC")
        summary = {}
        for e in events:
            rows = query(conn, "SELECT status, COUNT(*) c, SUM(paid_sen) paid FROM orders WHERE event_id=? GROUP BY status", (e["id"],))
            total_paid = sum((r["paid"] or 0) for r in rows)
            counts = {r["status"]: r["c"] for r in rows}
            summary[e["id"]] = {"counts": counts, "orders": sum(counts.values()), "paid": total_paid}
    return render(request, "admin/dashboard.html", {"events": events, "summary": summary, "rm": rm})


# --- event create / edit ---------------------------------------------------
@router.get("/events/new")
def event_new(request: Request):
    return render(request, "admin/event_form.html", {"event": None})


@router.post("/events/new")
def event_create(request: Request, name: str = Form(...), event_date: str = Form(""),
                 nextcloud_folder: str = Form(""), class_delimiter: str = Form(" - "),
                 close_date: str = Form(""), pickup_location: str = Form(""),
                 pay_bank_no: str = Form(""), pay_qrpay_image: str = Form(""),
                 postage_west: str = Form("10"), postage_east: str = Form("18")):
    with db() as conn:
        slug = unique_slug(conn, name)
        eid = conn.execute(
            """INSERT INTO events(slug, name, event_date, nextcloud_folder, class_delimiter,
                   close_date, pickup_location, pay_bank_no, pay_qrpay_image,
                   postage_west_sen, postage_east_sen)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (slug, name, event_date, nextcloud_folder.strip("/"), class_delimiter or " - ",
             close_date, pickup_location, pay_bank_no, pay_qrpay_image,
             to_sen(postage_west or 0), to_sen(postage_east or 0)),
        ).lastrowid
        audit(conn, admin_email(request), "event_created", "event", eid, name)
    return RedirectResponse(f"/admin/events/{eid}", status_code=303)


@router.get("/events/{event_id}")
def event_admin(event_id: int, request: Request):
    with db() as conn:
        event = one(conn, "SELECT * FROM events WHERE id=?", (event_id,))
        if not event:
            return render(request, "not_found.html", {})
        sizes = query(conn, "SELECT * FROM sizes WHERE event_id=? ORDER BY sort, price_sen", (event_id,))
        classes = query(conn, "SELECT c.*, (SELECT COUNT(*) FROM photos p WHERE p.class_id=c.id) n FROM classes c WHERE event_id=? ORDER BY school, name", (event_id,))
        nphotos = one(conn, "SELECT COUNT(*) c FROM photos WHERE event_id=?", (event_id,))["c"]
        session = one(conn, "SELECT * FROM print_sessions WHERE event_id=? AND active=1", (event_id,))
    return render(request, "admin/event.html", {
        "event": event, "sizes": sizes, "classes": classes, "nphotos": nphotos,
        "session": session, "rm": rm,
    })


@router.post("/events/{event_id}/edit")
def event_edit(event_id: int, request: Request, name: str = Form(...), event_date: str = Form(""),
               nextcloud_folder: str = Form(""), class_delimiter: str = Form(" - "),
               close_date: str = Form(""), status: str = Form("open"),
               pickup_location: str = Form(""), pay_bank_no: str = Form(""),
               pay_qrpay_image: str = Form(""), postage_west: str = Form("10"),
               postage_east: str = Form("18")):
    with db() as conn:
        conn.execute(
            """UPDATE events SET name=?, event_date=?, nextcloud_folder=?, class_delimiter=?,
                   close_date=?, status=?, pickup_location=?, pay_bank_no=?, pay_qrpay_image=?,
                   postage_west_sen=?, postage_east_sen=? WHERE id=?""",
            (name, event_date, nextcloud_folder.strip("/"), class_delimiter or " - ", close_date,
             status, pickup_location, pay_bank_no, pay_qrpay_image,
             to_sen(postage_west or 0), to_sen(postage_east or 0), event_id),
        )
        audit(conn, admin_email(request), "event_edited", "event", event_id, name)
    return RedirectResponse(f"/admin/events/{event_id}", status_code=303)


# --- sizes -----------------------------------------------------------------
@router.post("/events/{event_id}/sizes")
def size_add(event_id: int, code: str = Form(...), label: str = Form(""),
             price: str = Form("0"), sort: int = Form(0)):
    with db() as conn:
        conn.execute("INSERT INTO sizes(event_id, code, label, price_sen, sort) VALUES (?,?,?,?,?)",
                     (event_id, code.strip(), label.strip(), to_sen(price or 0), sort))
    return RedirectResponse(f"/admin/events/{event_id}", status_code=303)


@router.post("/sizes/{size_id}/delete")
def size_delete(size_id: int):
    with db() as conn:
        ev = one(conn, "SELECT event_id FROM sizes WHERE id=?", (size_id,))
        conn.execute("DELETE FROM sizes WHERE id=?", (size_id,))
    return RedirectResponse(f"/admin/events/{ev['event_id']}" if ev else "/admin", status_code=303)


# --- import from Nextcloud -------------------------------------------------
def import_event(event_id: int, actor: str) -> None:
    """Scan event folder (event > class > photos), build classes/photos/previews."""
    with db() as conn:
        event = one(conn, "SELECT * FROM events WHERE id=?", (event_id,))
    if not event or not nextcloud.is_configured():
        return
    base = event["nextcloud_folder"].strip("/")
    delim = event["class_delimiter"] or " - "
    added_photos = 0
    try:
        class_folders = nextcloud.subfolders(base)
        for ci, cf in enumerate(class_folders):
            school, cls_name = split_school_class(cf.name, delim)
            with db() as conn:
                existing = one(conn, "SELECT id FROM classes WHERE event_id=? AND folder_path=?",
                               (event_id, cf.path))
                if existing:
                    class_id = existing["id"]
                else:
                    class_id = conn.execute(
                        "INSERT INTO classes(event_id, school, name, folder_path, sort) VALUES (?,?,?,?,?)",
                        (event_id, school, cls_name, cf.path, ci)).lastrowid
            images = nextcloud.walk_images(cf.path)
            for pi, img in enumerate(images):
                with db() as conn:
                    seen = one(conn, "SELECT id, etag FROM photos WHERE event_id=? AND rel_path=?",
                               (event_id, img.path))
                    if seen and seen["etag"] == img.etag:
                        continue
                try:
                    data = nextcloud.download(img.path)
                    made = imaging.make_previews(data)
                except Exception:  # noqa: BLE001
                    log.exception("preview failed for %s", img.path)
                    continue
                with db() as conn:
                    if seen:
                        conn.execute(
                            "UPDATE photos SET etag=?, thumb_path=?, preview_path=?, width=?, height=? WHERE id=?",
                            (img.etag, made["thumb_path"], made["preview_path"], made["width"], made["height"], seen["id"]))
                    else:
                        conn.execute(
                            """INSERT INTO photos(event_id, class_id, filename, rel_path, etag,
                                   preview_path, thumb_path, width, height, sort)
                               VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (event_id, class_id, img.name, img.path, img.etag,
                             made["preview_path"], made["thumb_path"], made["width"], made["height"], pi))
                        added_photos += 1
    finally:
        with db() as conn:
            audit(conn, actor, "event_imported", "event", event_id, f"+{added_photos} photos")


@router.post("/events/{event_id}/import")
def event_import(event_id: int, request: Request, background: BackgroundTasks):
    background.add_task(import_event, event_id, admin_email(request))
    return RedirectResponse(f"/admin/events/{event_id}?import=started", status_code=303)


@router.post("/events/{event_id}/new-session")
def new_print_session(event_id: int, request: Request):
    """End the current print session so the next paid order opens a fresh sheet
    (use after you've cleared the print folder = new session)."""
    with db() as conn:
        sheets.end_session(conn, event_id)
        audit(conn, admin_email(request), "print_session_ended", "event", event_id, "")
    return RedirectResponse(f"/admin/events/{event_id}", status_code=303)


# --- orders ----------------------------------------------------------------
@router.get("/orders")
def admin_orders(request: Request):
    status = request.query_params.get("status", "")
    event_id = request.query_params.get("event", "")
    flagged = request.query_params.get("flagged", "")
    sql = ["SELECT o.*, e.name event_name, c.email, c.name cust_name FROM orders o",
           "JOIN events e ON e.id=o.event_id JOIN customers c ON c.id=o.customer_id WHERE 1=1"]
    params: list = []
    if status:
        sql.append("AND o.status=?"); params.append(status)
    if event_id:
        sql.append("AND o.event_id=?"); params.append(event_id)
    if flagged:
        sql.append("AND o.id IN (SELECT order_id FROM receipts WHERE duplicate=1 OR ocr_status='failed' OR forced=1)")
    sql.append("ORDER BY o.created_at DESC LIMIT 500")
    with db() as conn:
        orders = query(conn, " ".join(sql), params)
        events = query(conn, "SELECT id, name FROM events ORDER BY name")
    return render(request, "admin/orders.html",
                  {"orders": orders, "events": events, "rm": rm,
                   "f_status": status, "f_event": event_id, "f_flagged": flagged})


@router.get("/orders/{order_id}")
def admin_order(order_id: int, request: Request):
    with db() as conn:
        order = one(conn, "SELECT * FROM orders WHERE id=?", (order_id,))
        if not order:
            return render(request, "not_found.html", {})
        event = one(conn, "SELECT * FROM events WHERE id=?", (order["event_id"],))
        customer = one(conn, "SELECT * FROM customers WHERE id=?", (order["customer_id"],))
        items = query(conn, "SELECT * FROM order_items WHERE order_id=?", (order_id,))
        receipts = query(conn, "SELECT * FROM receipts WHERE order_id=? ORDER BY created_at", (order_id,))
        sizes = query(conn, "SELECT * FROM sizes WHERE event_id=? ORDER BY sort", (order["event_id"],))
    return render(request, "admin/order.html", {
        "order": order, "event": event, "customer": customer, "items": items,
        "receipts": receipts, "sizes": sizes, "rm": rm,
    })


@router.post("/orders/{order_id}/mark-paid")
def admin_mark_paid(order_id: int, request: Request, background: BackgroundTasks):
    from ..orders_service import finalize_payment
    with db() as conn:
        conn.execute("UPDATE orders SET status='paid', updated_at=datetime('now') WHERE id=?", (order_id,))
        audit(conn, admin_email(request), "order_marked_paid", "order", order_id, "")
    background.add_task(finalize_payment, order_id)
    return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)


@router.post("/orders/{order_id}/status")
def admin_set_status(order_id: int, request: Request, status: str = Form(...)):
    with db() as conn:
        conn.execute("UPDATE orders SET status=?, updated_at=datetime('now') WHERE id=?", (status, order_id))
        audit(conn, admin_email(request), "order_status", "order", order_id, status)
    return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)


@router.post("/orders/{order_id}/override-amount")
def admin_override_amount(order_id: int, request: Request, amount: str = Form(...)):
    with db() as conn:
        conn.execute("UPDATE orders SET paid_sen=?, updated_at=datetime('now') WHERE id=?",
                     (to_sen(amount or 0), order_id))
        audit(conn, admin_email(request), "order_override_amount", "order", order_id, amount)
    return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)


@router.post("/items/{item_id}/update")
def admin_item_update(item_id: int, request: Request, qty: int = Form(...), size_id: int = Form(...)):
    oid = None
    with db() as conn:
        item = one(conn, "SELECT * FROM order_items WHERE id=?", (item_id,))
        size = one(conn, "SELECT * FROM sizes WHERE id=?", (size_id,))
        if item:
            oid = item["order_id"]
        if item and size:
            conn.execute("UPDATE order_items SET qty=?, size_id=?, unit_price_sen=?, size_code=? WHERE id=?",
                         (max(1, qty), size_id, size["price_sen"], size["code"], item_id))
            compute_order_totals(conn, item["order_id"])
            audit(conn, admin_email(request), "item_updated", "order", item["order_id"], str(item_id))
    return RedirectResponse(f"/admin/orders/{oid}" if oid else "/admin/orders", status_code=303)


@router.post("/orders/{order_id}/cancel")
def admin_cancel(order_id: int, request: Request, reason: str = Form("")):
    with db() as conn:
        conn.execute("UPDATE orders SET status='cancelled', cancel_reason=?, updated_at=datetime('now') WHERE id=?",
                     (reason, order_id))
        audit(conn, admin_email(request), "order_cancelled", "order", order_id, reason)
    return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)


@router.post("/orders/{order_id}/reprint")
def admin_reprint(order_id: int, request: Request, background: BackgroundTasks):
    def _job(oid):
        with db() as conn:
            try:
                printing.copy_order_to_print(conn, oid)
                session_row = sheets.get_or_create_session(conn, one(conn, "SELECT event_id FROM orders WHERE id=?", (oid,))["event_id"])
                sheets.append_order(conn, oid, session_row)
            except Exception:  # noqa: BLE001
                log.exception("reprint failed")
    background.add_task(_job, order_id)
    with db() as conn:
        audit(conn, admin_email(request), "order_reprint", "order", order_id, "")
    return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)


# --- maintenance -----------------------------------------------------------
@router.post("/trash/clear")
def admin_clear_trash(request: Request):
    n = backup.clear_trash_all()
    with db() as conn:
        audit(conn, admin_email(request), "trash_cleared", "system", "", str(n))
    return RedirectResponse("/admin", status_code=303)


@router.get("/receipt/{receipt_id}")
def admin_receipt_image(receipt_id: int):
    from fastapi.responses import FileResponse, Response
    with db() as conn:
        r = one(conn, "SELECT stored_path FROM receipts WHERE id=?", (receipt_id,))
    if not r or not r["stored_path"]:
        return Response(status_code=404)
    full = settings.data_path / r["stored_path"]
    if not full.exists():
        return Response(status_code=404)
    return FileResponse(full, media_type="image/webp")


@router.get("/audit")
def admin_audit(request: Request):
    with db() as conn:
        rows = query(conn, "SELECT * FROM audit_log ORDER BY id DESC LIMIT 300")
    return render(request, "admin/audit.html", {"rows": rows})
