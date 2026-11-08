"""Admin panel. Mounted under /admin and protected by Cloudflare Access
(no application-level auth). The authenticated email (from the CF header) is
used only for the audit log.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse

from .. import backup, batches, event_access, imaging, nextcloud
from ..config import settings
from ..database import audit, db, get_setting, one, query, set_setting
from ..deps import public_base, render
from ..pricing import compute_order_totals
from ..email_send import send_receipt_rejected
from ..orders_service import (after_receipt, customer_wa_link, mark_refunded, pending_receipt_ids,
                              reject_receipt, rerun_receipt, rescan_pending)
from ..utils import clean_pickup_text, rm, split_school_class, to_sen, unique_slug

log = logging.getLogger("admin")
router = APIRouter(prefix="/admin")


def admin_email(request: Request) -> str:
    return request.headers.get(settings.admin_email_header, "admin@local")


async def _qr_from_upload(qr_file: UploadFile | None, event_id: int) -> str | None:
    """Store an uploaded QR image; None if no file was chosen."""
    if qr_file is None or not qr_file.filename:
        return None
    data = await qr_file.read()
    if not data:
        return None
    return imaging.save_qr_image(data, event_id)


def _delivery_flags(allow_pickup: str, allow_post: str) -> tuple[int, int]:
    """At least one delivery option stays on; with none ticked, fall back to pickup."""
    pick, post = int(bool(allow_pickup)), int(bool(allow_post))
    if not pick and not post:
        pick = 1
    return pick, post


# --- dashboard -------------------------------------------------------------
@router.get("")
@router.get("/")
def dashboard(request: Request):
    with db() as conn:
        events = query(conn, "SELECT * FROM events ORDER BY created_at DESC")
        summary = {}
        for e in events:
            rows = query(conn, "SELECT status, COUNT(*) c, SUM(paid_sen) paid FROM orders WHERE event_id=? AND deleted_at IS NULL GROUP BY status", (e["id"],))
            total_paid = sum((r["paid"] or 0) for r in rows)
            counts = {r["status"]: r["c"] for r in rows}
            summary[e["id"]] = {"counts": counts, "orders": sum(counts.values()), "paid": total_paid}
    return render(request, "admin/dashboard.html", {"events": events, "summary": summary, "rm": rm})


# --- event create / edit ---------------------------------------------------
@router.get("/events/new")
def event_new(request: Request):
    return render(request, "admin/event_form.html",
                  {"event": None, "instances": settings.nc_instances()})


@router.post("/events/new")
async def event_create(request: Request, name: str = Form(...), event_date: str = Form(""),
                 nextcloud_id: str = Form(""), nextcloud_folder: str = Form(""),
                 class_delimiter: str = Form(" - "),
                 close_date: str = Form(""), pickup_location: str = Form(""),
                 pay_bank_no: str = Form(""), pay_qrpay_image: str = Form(""),
                 qr_file: UploadFile | None = File(None),
                 postage_west: str = Form("10"), postage_east: str = Form("18"),
                 allow_pickup: str = Form(""), allow_post: str = Form("")):
    pick, post = _delivery_flags(allow_pickup, allow_post)
    pickup_location = clean_pickup_text(pickup_location)
    with db() as conn:
        slug = unique_slug(conn, name)
        eid = conn.execute(
            """INSERT INTO events(slug, name, event_date, nextcloud_id, nextcloud_folder,
                   class_delimiter, close_date, pickup_location, pay_bank_no, pay_qrpay_image,
                   postage_west_sen, postage_east_sen, allow_pickup, allow_post)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (slug, name, event_date, nextcloud_id, nextcloud_folder.strip("/"),
             class_delimiter or " - ", close_date, pickup_location, pay_bank_no, pay_qrpay_image,
             to_sen(postage_west or 0), to_sen(postage_east or 0), pick, post),
        ).lastrowid
        audit(conn, admin_email(request), "event_created", "event", eid, name)
    try:
        qr_url = await _qr_from_upload(qr_file, eid)
    except ValueError:
        return RedirectResponse(f"/admin/events/{eid}?qr_error=1", status_code=303)
    if qr_url:
        with db() as conn:
            conn.execute("UPDATE events SET pay_qrpay_image=? WHERE id=?", (qr_url, eid))
            audit(conn, admin_email(request), "event_qr_uploaded", "event", eid, qr_url)
    return RedirectResponse(f"/admin/events/{eid}", status_code=303)


@router.get("/nc/browse")
def nc_browse(request: Request):
    """List subfolders of a Nextcloud instance (for the event folder picker)."""
    iid = request.query_params.get("instance", "")
    path = request.query_params.get("path", "")
    inst = settings.nc_instance(iid or None)
    if not inst:
        return JSONResponse({"error": "no_instance", "folders": []})
    try:
        folders = [{"name": e.name, "path": e.path} for e in nextcloud.subfolders(inst, path)]
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}", "folders": []})
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    return JSONResponse({"path": path, "parent": parent, "has_parent": bool(path),
                         "folders": folders})


@router.get("/events/{event_id}")
def event_admin(event_id: int, request: Request):
    with db() as conn:
        event = one(conn, "SELECT * FROM events WHERE id=?", (event_id,))
        if not event:
            return render(request, "not_found.html", {})
        if not event["access_key"]:   # every event gets a secret direct link
            conn.execute("UPDATE events SET access_key=? WHERE id=?", (event_access.new_key(), event_id))
            event = one(conn, "SELECT * FROM events WHERE id=?", (event_id,))
        sizes = query(conn, "SELECT * FROM sizes WHERE event_id=? ORDER BY sort, price_sen", (event_id,))
        classes = query(conn, "SELECT c.*, (SELECT COUNT(*) FROM photos p WHERE p.class_id=c.id) n FROM classes c WHERE event_id=? ORDER BY school, name", (event_id,))
        nphotos = one(conn, "SELECT COUNT(*) c FROM photos WHERE event_id=?", (event_id,))["c"]
        bsum = batches.summary(conn, event_id)
    return render(request, "admin/event.html", {
        "event": event, "sizes": sizes, "classes": classes, "nphotos": nphotos,
        "bsum": bsum, "rm": rm, "instances": settings.nc_instances(),
        "locked": event_access.is_locked(event),
        "direct_url": event_access.direct_url(public_base(request), event),
    })


@router.post("/events/{event_id}/edit")
async def event_edit(event_id: int, request: Request, name: str = Form(...), event_date: str = Form(""),
               nextcloud_id: str = Form(""), nextcloud_folder: str = Form(""),
               class_delimiter: str = Form(" - "),
               close_date: str = Form(""), status: str = Form("open"),
               pickup_location: str = Form(""), pay_bank_no: str = Form(""),
               pay_qrpay_image: str = Form(""), postage_west: str = Form("10"),
               postage_east: str = Form("18"), qr_file: UploadFile | None = File(None),
               qr_remove: str = Form(""), allow_pickup: str = Form(""),
               allow_post: str = Form(""), access_password: str = Form("")):
    pick, post = _delivery_flags(allow_pickup, allow_post)
    pickup_location = clean_pickup_text(pickup_location)
    qr_error = False
    try:
        qr_url = await _qr_from_upload(qr_file, event_id)
    except ValueError:
        qr_url, qr_error = None, True
    if qr_url:
        pay_qrpay_image = qr_url
    elif qr_remove:
        pay_qrpay_image = ""
    with db() as conn:
        conn.execute(
            """UPDATE events SET name=?, event_date=?, nextcloud_id=?, nextcloud_folder=?,
                   class_delimiter=?, close_date=?, status=?, pickup_location=?, pay_bank_no=?,
                   pay_qrpay_image=?, postage_west_sen=?, postage_east_sen=?,
                   allow_pickup=?, allow_post=?, access_password=? WHERE id=?""",
            (name, event_date, nextcloud_id, nextcloud_folder.strip("/"), class_delimiter or " - ",
             close_date, status, pickup_location, pay_bank_no, pay_qrpay_image,
             to_sen(postage_west or 0), to_sen(postage_east or 0), pick, post,
             access_password.strip()[:64], event_id),
        )
        audit(conn, admin_email(request), "event_edited", "event", event_id, name)
        if qr_url:
            audit(conn, admin_email(request), "event_qr_uploaded", "event", event_id, qr_url)
    suffix = "?qr_error=1" if qr_error else ""
    return RedirectResponse(f"/admin/events/{event_id}{suffix}", status_code=303)


@router.post("/events/{event_id}/rotate-link")
def event_rotate_link(event_id: int, request: Request):
    """New secret key: the old direct link and everyone's saved access stop working."""
    with db() as conn:
        conn.execute("UPDATE events SET access_key=? WHERE id=?", (event_access.new_key(), event_id))
        audit(conn, admin_email(request), "event_link_rotated", "event", event_id, "")
    return RedirectResponse(f"/admin/events/{event_id}?link=new", status_code=303)


@router.get("/events/{event_id}/share")
def event_share(event_id: int, request: Request):
    """Big QR + link + password to show on screen, print or screenshot."""
    with db() as conn:
        event = one(conn, "SELECT * FROM events WHERE id=?", (event_id,))
    if not event:
        return render(request, "not_found.html", {})
    url = f"{public_base(request)}/e/{event['slug']}"
    try:
        qr = event_access.qr_svg(url)
    except Exception:  # noqa: BLE001
        log.exception("share QR failed for event %s", event_id)
        qr = ""
    return render(request, "admin/event_share.html", {
        "event": event, "url": url, "qr": qr, "locked": event_access.is_locked(event),
    })


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
    if not event:
        return
    inst = settings.nc_instance(event["nextcloud_id"])
    if not inst:
        return
    base = event["nextcloud_folder"].strip("/")
    delim = event["class_delimiter"] or " - "
    added_photos = 0
    try:
        class_folders = nextcloud.subfolders(inst, base)
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
            images = nextcloud.walk_images(inst, cf.path)
            for pi, img in enumerate(images):
                with db() as conn:
                    seen = one(conn, "SELECT id, etag FROM photos WHERE event_id=? AND rel_path=?",
                               (event_id, img.path))
                    if seen and seen["etag"] == img.etag:
                        continue
                try:
                    data = nextcloud.download(inst, img.path)
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


# --- print batches -----------------------------------------------------------
@router.post("/batches/{batch_id}/close")
def batch_close(batch_id: int, request: Request, background: BackgroundTasks):
    """Close the batch: arrange its files in Nextcloud (background), next paid
    orders go into a new batch."""
    with db() as conn:
        b = one(conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
        ok = batches.start_close(conn, batch_id, admin_email(request))
    if ok:
        background.add_task(batches.arrange, batch_id)
    return RedirectResponse(f"/admin/events/{b['event_id']}?batch={'closing' if ok else 'not_open'}#batches"
                            if b else "/admin", status_code=303)


@router.post("/batches/{batch_id}/arrange")
def batch_rearrange(batch_id: int, request: Request, background: BackgroundTasks):
    """Arrange a closed batch again (e.g. after an error, or files were moved)."""
    with db() as conn:
        b = one(conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
        if b and b["status"] != "open":
            conn.execute("UPDATE batches SET status='closing', error='' WHERE id=?", (batch_id,))
            audit(conn, admin_email(request), "batch_rearrange", "event", b["event_id"], f"Batch {b['number']}")
    if b and b["status"] != "open":
        background.add_task(batches.arrange, batch_id)
    return RedirectResponse(f"/admin/events/{b['event_id']}?batch=closing#batches" if b else "/admin",
                            status_code=303)


@router.get("/batches/{batch_id}/list.csv")
def batch_list_csv(batch_id: int):
    from fastapi.responses import Response
    with db() as conn:
        b = one(conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
        if not b:
            return Response(status_code=404)
        data = batches.batch_csv(batches.batch_lines(conn, batch_id), b["number"])
    return Response(data, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="senarai-batch-{b["number"]}.csv"'})


@router.get("/events/{event_id}/sheet.xlsx")
def event_sheet(event_id: int):
    from fastapi.responses import Response
    with db() as conn:
        ev = one(conn, "SELECT slug FROM events WHERE id=?", (event_id,))
        if not ev:
            return Response(status_code=404)
        data = batches.build_sheet(conn, event_id)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="Senarai-Order-{ev["slug"]}.xlsx"'})


# --- orders ----------------------------------------------------------------
@router.get("/orders")
def admin_orders(request: Request):
    status = request.query_params.get("status", "")
    event_id = request.query_params.get("event", "")
    flagged = request.query_params.get("flagged", "")
    trash = request.query_params.get("view", "") == "trash"
    sql = ["SELECT o.*, e.name event_name, c.email, c.name cust_name,",
           "(SELECT number FROM batches b WHERE b.id=o.batch_id) batch_no,",
           "(SELECT COUNT(*) FROM receipts r WHERE r.order_id=o.id) n_receipts,",
           "(SELECT r.ocr_note FROM receipts r WHERE r.order_id=o.id ORDER BY r.id DESC LIMIT 1) last_note",
           "FROM orders o",
           "JOIN events e ON e.id=o.event_id JOIN customers c ON c.id=o.customer_id WHERE 1=1",
           "AND o.deleted_at IS NOT NULL" if trash else "AND o.deleted_at IS NULL"]
    params: list = []
    if status:
        sql.append("AND o.status=?"); params.append(status)
    if event_id:
        sql.append("AND o.event_id=?"); params.append(event_id)
    if flagged:
        sql.append("AND (o.id IN (SELECT order_id FROM receipts WHERE rejected=0 AND "
                   "(accepted=0 OR duplicate=1 OR forced=1 OR ocr_note IN ('partial','over'))) "
                   "OR (o.paid_sen > o.total_sen AND o.refunded_sen=0))")
    sql.append("ORDER BY o.deleted_at DESC" if trash else "ORDER BY o.created_at DESC")
    sql.append("LIMIT 500")
    with db() as conn:
        orders = query(conn, " ".join(sql), params)
        events = query(conn, "SELECT id, name FROM events ORDER BY name")
        n_trash = one(conn, "SELECT COUNT(*) c FROM orders WHERE deleted_at IS NOT NULL")["c"]
        n_pending = len(pending_receipt_ids(conn))
        n_check = one(conn, """SELECT COUNT(*) c FROM receipts r JOIN orders o ON o.id=r.order_id
                               WHERE o.deleted_at IS NULL AND o.status='reviewing'
                                 AND r.rejected=0 AND r.accepted=0""")["c"]
        n_refund = one(conn, """SELECT COUNT(*) c FROM orders WHERE deleted_at IS NULL
                                AND paid_sen > total_sen AND refunded_sen=0
                                AND status IN ('paid','printing','ready','reviewing')""")["c"]
    return render(request, "admin/orders.html",
                  {"orders": orders, "events": events, "rm": rm, "trash": trash,
                   "n_trash": n_trash, "n_pending": n_pending, "n_check": n_check, "n_refund": n_refund, "protected": PROTECTED_STATUSES,
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
        batch = one(conn, "SELECT * FROM batches WHERE id=?", (order["batch_id"],)) if order["batch_id"] else None
    phone = customer["phone"] if customer else ""
    last_rej = next((r for r in reversed(receipts) if r["rejected"]), None)
    wa = {"rejected": customer_wa_link(order, phone, "rejected", last_rej["reject_reason"]) if last_rej else "",
          "balance": customer_wa_link(order, phone, "balance") if 0 < order["paid_sen"] < order["total_sen"] else "",
          "refund": customer_wa_link(order, phone, "refund") if order["paid_sen"] > order["total_sen"] else "",
          "chat": customer_wa_link(order, phone, "chat")}
    return render(request, "admin/order.html", {
        "order": order, "event": event, "customer": customer, "items": items,
        "receipts": receipts, "sizes": sizes, "rm": rm, "wa": wa, "batch": batch,
        "batch_link": batches.files_link(batch["folder"]) if batch and batch["folder"] else "",
        "needs_double": _needs_double(order, len(receipts)),
    })


@router.post("/orders/{order_id}/mark-paid")
def admin_mark_paid(order_id: int, request: Request, background: BackgroundTasks):
    from ..orders_service import finalize_payment
    with db() as conn:
        conn.execute("UPDATE orders SET status='paid', paid_sen=MAX(paid_sen, total_sen), "
                     "updated_at=datetime('now') WHERE id=?", (order_id,))
        audit(conn, admin_email(request), "order_marked_paid", "order", order_id, "")
    background.add_task(finalize_payment, order_id)
    return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)


@router.post("/orders/{order_id}/status")
def admin_set_status(order_id: int, request: Request, status: str = Form(...)):
    with db() as conn:
        conn.execute("UPDATE orders SET status=?, updated_at=datetime('now') WHERE id=?", (status, order_id))
        audit(conn, admin_email(request), "order_status", "order", order_id, status)
        if status == "paid":
            batches.assign_order(conn, order_id)
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
    """Arrange this order's batch again (only for a closed batch)."""
    with db() as conn:
        o = one(conn, "SELECT batch_id FROM orders WHERE id=?", (order_id,))
        b = one(conn, "SELECT * FROM batches WHERE id=?", (o["batch_id"],)) if o and o["batch_id"] else None
        if b and b["status"] != "open":
            conn.execute("UPDATE batches SET status='closing', error='' WHERE id=?", (b["id"],))
            audit(conn, admin_email(request), "batch_rearrange", "order", order_id, f"Batch {b['number']}")
    if b and b["status"] != "open":
        background.add_task(batches.arrange, b["id"])
    return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)


# --- delete / trash ---------------------------------------------------------
# Orders with money involved need a second confirmation to delete.
PROTECTED_STATUSES = ("reviewing", "paid", "printing", "ready")


def _needs_double(order, n_receipts: int) -> bool:
    return order["status"] in PROTECTED_STATUSES or n_receipts > 0


@router.post("/orders/{order_id}/delete")
def admin_delete(order_id: int, request: Request, confirm2: str = Form(""), back: str = Form("")):
    with db() as conn:
        order = one(conn, "SELECT * FROM orders WHERE id=? AND deleted_at IS NULL", (order_id,))
        if not order:
            return RedirectResponse("/admin/orders", status_code=303)
        n = one(conn, "SELECT COUNT(*) c FROM receipts WHERE order_id=?", (order_id,))["c"]
        if _needs_double(order, n) and confirm2 != order["order_no"]:
            return RedirectResponse(f"/admin/orders/{order_id}?need_confirm=1", status_code=303)
        actor = admin_email(request)
        conn.execute("UPDATE orders SET deleted_at=datetime('now'), deleted_by=? WHERE id=?",
                     (actor, order_id))
        audit(conn, actor, "order_deleted", "order", order_id, f"{order['order_no']} ({order['status']})")
    dest = back if back.startswith("/admin/orders") and not back.startswith(f"/admin/orders/{order_id}") else "/admin/orders"
    return RedirectResponse(dest + ("&" if "?" in dest else "?") + "deleted=" + order["order_no"], status_code=303)


@router.post("/orders/{order_id}/restore")
def admin_restore(order_id: int, request: Request):
    with db() as conn:
        conn.execute("UPDATE orders SET deleted_at=NULL, deleted_by='' WHERE id=?", (order_id,))
        audit(conn, admin_email(request), "order_restored", "order", order_id, "")
    return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)


@router.post("/orders/{order_id}/purge")
def admin_purge(order_id: int, request: Request, confirm2: str = Form("")):
    """Delete for good (only from Trash). Receipt images go too."""
    with db() as conn:
        order = one(conn, "SELECT * FROM orders WHERE id=? AND deleted_at IS NOT NULL", (order_id,))
        if not order or confirm2 != order["order_no"]:
            return RedirectResponse("/admin/orders?view=trash", status_code=303)
        files = [r["stored_path"] for r in query(conn, "SELECT stored_path FROM receipts WHERE order_id=?", (order_id,))]
        conn.execute("DELETE FROM receipts WHERE order_id=?", (order_id,))
        conn.execute("DELETE FROM order_items WHERE order_id=?", (order_id,))
        conn.execute("DELETE FROM orders WHERE id=?", (order_id,))
        audit(conn, admin_email(request), "order_purged", "order", order_id, order["order_no"])
    for f in files:
        if f:
            (settings.data_path / f).unlink(missing_ok=True)
    return RedirectResponse("/admin/orders?view=trash", status_code=303)


# --- receipt OCR (re-run) ----------------------------------------------------
@router.post("/receipts/{receipt_id}/rerun")
def admin_rerun_receipt(receipt_id: int, request: Request, background: BackgroundTasks):
    with db() as conn:
        state = rerun_receipt(conn, receipt_id)
        if state:
            audit(conn, admin_email(request), "receipt_rerun", "order", state["order_id"], str(receipt_id))
    if not state:
        return RedirectResponse("/admin/orders", status_code=303)
    if state.get("just_paid"):
        background.add_task(after_receipt, state["order_id"], state)
    return RedirectResponse(f"/admin/orders/{state['order_id']}?rerun={state['note']}", status_code=303)


@router.post("/receipts/rescan")
def admin_rescan(request: Request, background: BackgroundTasks):
    background.add_task(rescan_pending, False)
    with db() as conn:
        audit(conn, admin_email(request), "receipt_rescan_all", "system", "", "")
    return RedirectResponse("/admin/orders?rescan=started", status_code=303)


@router.post("/receipts/{receipt_id}/reject")
def admin_reject_receipt(receipt_id: int, request: Request, background: BackgroundTasks,
                         reason: str = Form(...)):
    reason = reason.strip()
    with db() as conn:
        r = one(conn, "SELECT order_id FROM receipts WHERE id=?", (receipt_id,))
        if not r or not reason:
            return RedirectResponse(f"/admin/orders/{r['order_id']}?reject_error=1" if r else "/admin/orders",
                                    status_code=303)
        state = reject_receipt(conn, receipt_id, reason, admin_email(request))
        o = one(conn, "SELECT o.*, c.email FROM orders o JOIN customers c ON c.id=o.customer_id WHERE o.id=?",
                (state["order_id"],))
    due = max(0, o["total_sen"] - o["paid_sen"])
    background.add_task(_safe_mail, send_receipt_rejected, o["email"], o["order_no"], reason, due,
                        f"{settings.base_url}/order/{o['order_no']}")
    return RedirectResponse(f"/admin/orders/{o['id']}?rejected=1", status_code=303)


@router.post("/orders/{order_id}/refunded")
def admin_refunded(order_id: int, request: Request):
    with db() as conn:
        mark_refunded(conn, order_id, admin_email(request))
    return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)


def _safe_mail(fn, *args) -> None:
    try:
        fn(*args)
    except Exception:  # noqa: BLE001
        log.exception("email failed: %s", getattr(fn, "__name__", fn))


# --- settings (DeepSeek API, notify email) ------------------------------------
def _mask(key: str) -> str:
    return ("•" * 8 + key[-4:]) if key else ""


@router.get("/settings")
def settings_page(request: Request):
    from ..ocr import ai_config
    with db() as conn:
        cfg = ai_config(conn)
        notify = get_setting(conn, "admin_notify_email", settings.admin_notify_email)
        from_db = bool(get_setting(conn, "deepseek_api_key", ""))
    import shutil as _sh
    return render(request, "admin/settings.html", {
        "cfg": cfg, "key_mask": _mask(cfg["key"]), "key_from_db": from_db, "notify": notify,
        "tesseract": bool(_sh.which("tesseract")),
    })


@router.post("/settings")
def settings_save(request: Request, background: BackgroundTasks,
                  deepseek_api_key: str = Form(""), deepseek_model: str = Form("deepseek-flash"),
                  deepseek_base_url: str = Form("https://api.deepseek.com"),
                  admin_notify_email: str = Form(""), clear_key: str = Form("")):
    with db() as conn:
        if clear_key:
            set_setting(conn, "deepseek_api_key", "")
        elif deepseek_api_key.strip():
            set_setting(conn, "deepseek_api_key", deepseek_api_key.strip())
        set_setting(conn, "deepseek_model", deepseek_model.strip() or "deepseek-flash")
        set_setting(conn, "deepseek_base_url", deepseek_base_url.strip() or "https://api.deepseek.com")
        set_setting(conn, "admin_notify_email", admin_notify_email.strip())
        audit(conn, admin_email(request), "settings_saved", "system", "",
              "key changed" if deepseek_api_key.strip() or clear_key else "")
    if deepseek_api_key.strip():
        background.add_task(rescan_pending, False)  # new key: re-check stuck receipts now
    return RedirectResponse("/admin/settings?saved=1", status_code=303)


@router.post("/settings/test")
def settings_test(request: Request):
    """Send a sample receipt IMAGE (RM4.00) to DeepSeek and check it reads the amount."""
    import tempfile
    from pathlib import Path

    from PIL import Image, ImageDraw, ImageFont

    from ..ocr import ai_config, ai_parse
    lines = ["Maybank2u", "Transfer Successful", "Amount RM 4.00",
             "Recipient PROMEDIA CREATIVE SOLUTIONS", "Reference No. 7712345678",
             "Date 06 Nov 2026 10:21:05"]
    with db() as conn:
        cfg = ai_config(conn)
    with tempfile.TemporaryDirectory() as tmp:
        img = Image.new("RGB", (900, 560), "white")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.load_default(size=36)
        except TypeError:
            font = ImageFont.load_default()
        for i, ln in enumerate(lines):
            draw.text((40, 30 + i * 85), ln, fill="black", font=font)
        path = Path(tmp) / "sample.png"
        img.save(path)
        ai = ai_parse("", cfg, path)   # image only: proves the model reads pictures
    amount = str((ai or {}).get("amount") or "").replace("RM", "").strip()
    ok = bool(ai) and ai.get("_vision") and amount in ("4.00", "4", "4.0")
    return RedirectResponse(f"/admin/settings?test={'ok' if ok else 'fail'}", status_code=303)


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


# --- home-page carousel ----------------------------------------------------
@router.get("/slides")
def slides_admin(request: Request):
    with db() as conn:
        slides = query(conn, "SELECT * FROM slides ORDER BY sort, id")
    return render(request, "admin/slides.html", {"slides": slides})


@router.post("/slides")
async def slides_upload(request: Request, files: list[UploadFile] = File(...)):
    saved, bad = 0, 0
    for f in files:
        if not f.filename:
            continue
        try:
            name = imaging.save_slide_image(await f.read())
        except ValueError:
            bad += 1
            continue
        with db() as conn:
            top = one(conn, "SELECT COALESCE(MAX(sort), 0) m FROM slides")["m"]
            sid = conn.execute("INSERT INTO slides(file, sort) VALUES (?,?)", (name, top + 1)).lastrowid
            audit(conn, admin_email(request), "slide_added", "slide", sid, f.filename)
        saved += 1
    return RedirectResponse(f"/admin/slides?saved={saved}&bad={bad}", status_code=303)


@router.post("/slides/{slide_id}/update")
def slide_update(slide_id: int, request: Request, caption: str = Form(""), active: str = Form("")):
    with db() as conn:
        conn.execute("UPDATE slides SET caption=?, active=? WHERE id=?",
                     (caption.strip(), int(bool(active)), slide_id))
        audit(conn, admin_email(request), "slide_edited", "slide", slide_id, caption.strip())
    return RedirectResponse("/admin/slides", status_code=303)


@router.post("/slides/{slide_id}/move")
def slide_move(slide_id: int, request: Request, direction: str = Form("up")):
    with db() as conn:
        rows = [r["id"] for r in query(conn, "SELECT id FROM slides ORDER BY sort, id")]
        if slide_id in rows:
            i = rows.index(slide_id)
            j = i - 1 if direction == "up" else i + 1
            if 0 <= j < len(rows):
                rows[i], rows[j] = rows[j], rows[i]
            for pos, sid in enumerate(rows, start=1):
                conn.execute("UPDATE slides SET sort=? WHERE id=?", (pos, sid))
    return RedirectResponse("/admin/slides", status_code=303)


@router.post("/slides/{slide_id}/delete")
def slide_delete(slide_id: int, request: Request):
    with db() as conn:
        row = one(conn, "SELECT file FROM slides WHERE id=?", (slide_id,))
        if row:
            conn.execute("DELETE FROM slides WHERE id=?", (slide_id,))
            audit(conn, admin_email(request), "slide_deleted", "slide", slide_id, row["file"])
            still_used = one(conn, "SELECT 1 FROM slides WHERE file=?", (row["file"],))
            if not still_used:
                (settings.slides_dir / row["file"]).unlink(missing_ok=True)
    return RedirectResponse("/admin/slides", status_code=303)
