"""Print batches (per event) + the event's main spreadsheet.

Flow (rafi, 2026-11-06):
- A paid order joins the event's OPEN batch (Batch 1, 2, 3 …). Nothing is copied yet.
- Admin closes the batch -> the files are arranged in the print instance's
  Nextcloud under

      <PRINT_FOLDER>/<event-slug>/Batch-<N>/<SIZE>/<copies>salinan/<original filename>

  The same photo bought by several orders in the batch is ONE file; its copies are
  summed (A 1x + B 2x -> 3salinan). A batch list (senarai-batch-<N>.csv) goes in the
  batch folder, and the batch's paid orders move to 'printing'.
- The event's main spreadsheet (Senarai-Order-<slug>.xlsx: all orders, items,
  batch summary) is rewritten in <PRINT_FOLDER>/<event-slug>/ after each payment and
  each batch close, and can be downloaded from admin at any time.
"""
from __future__ import annotations

import csv
import io
import logging
import posixpath
from collections import OrderedDict
from urllib.parse import quote

from . import nextcloud
from .config import settings
from .database import audit, db, one, query
from .utils import local_now, rm

log = logging.getLogger("batches")

CONTENT_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".tif": "image/tiff", ".tiff": "image/tiff",
}
BATCHED_STATUSES = ("paid", "printing", "ready")


# --- paths / links ------------------------------------------------------------
def event_folder(slug: str) -> str:
    return f"{settings.nextcloud_print_folder.strip('/')}/{slug}"


def batch_folder(slug: str, number: int) -> str:
    return f"{event_folder(slug)}/Batch-{number}"


def sheet_path(slug: str) -> str:
    return f"{event_folder(slug)}/Senarai-Order-{slug}.xlsx"


def files_link(path: str) -> str:
    """Link that opens a folder in the print instance's Nextcloud web UI."""
    inst = settings.nc_print_instance()
    if not inst:
        return ""
    return f"{inst['base_url'].rstrip('/')}/apps/files/?dir={quote('/' + path.strip('/'))}"


# --- batch membership -----------------------------------------------------------
def open_batch(conn, event_id: int):
    """The event's open batch, created (next number) when there is none."""
    row = one(conn, "SELECT * FROM batches WHERE event_id=? AND status='open'", (event_id,))
    if row:
        return row
    n = one(conn, "SELECT COALESCE(MAX(number),0)+1 n FROM batches WHERE event_id=?", (event_id,))["n"]
    bid = conn.execute("INSERT INTO batches(event_id, number) VALUES (?,?)", (event_id, n)).lastrowid
    return one(conn, "SELECT * FROM batches WHERE id=?", (bid,))


def assign_order(conn, order_id: int):
    """Put a paid order into its event's open batch (no-op if already in one)."""
    o = one(conn, "SELECT * FROM orders WHERE id=?", (order_id,))
    if not o or o["batch_id"]:
        return None
    b = open_batch(conn, o["event_id"])
    conn.execute("UPDATE orders SET batch_id=? WHERE id=?", (b["id"], order_id))
    audit(conn, "system", "order_batched", "order", order_id, f"Batch {b['number']}")
    return b


def backfill(conn) -> int:
    """Paid orders that never joined a batch (before batches existed) join the open one."""
    rows = query(conn, "SELECT id FROM orders WHERE status='paid' AND batch_id IS NULL "
                       "AND deleted_at IS NULL ORDER BY id")
    for r in rows:
        assign_order(conn, r["id"])
    return len(rows)


def batch_orders(conn, batch_id: int):
    return query(conn, f"""SELECT * FROM orders WHERE batch_id=? AND deleted_at IS NULL
                           AND status IN {BATCHED_STATUSES} ORDER BY id""", (batch_id,))


def batch_lines(conn, batch_id: int) -> list[dict]:
    """One line per order item in the batch, with customer + order details."""
    rows = query(conn, f"""SELECT i.*, o.order_no, o.delivery_method, o.pickup_location, o.address,
                                  o.phone_used, c.name cust_name, c.email cust_email, c.phone cust_phone
                           FROM order_items i JOIN orders o ON o.id=i.order_id
                           JOIN customers c ON c.id=o.customer_id
                           WHERE o.batch_id=? AND o.deleted_at IS NULL AND o.status IN {BATCHED_STATUSES}
                           ORDER BY o.order_no, i.id""", (batch_id,))
    return [dict(r) for r in rows]


def plan_files(lines: list[dict]) -> list[dict]:
    """Group the batch into print files: one per (photo, size), copies summed.
    Two DIFFERENT photos with the same file name in one folder get the class added."""
    groups: "OrderedDict[tuple, dict]" = OrderedDict()
    for ln in lines:
        key = (ln["photo_id"], ln["size_code"])
        g = groups.setdefault(key, {"photo_id": ln["photo_id"], "rel_path": ln["rel_path"],
                                    "filename": ln["filename"], "class_name": ln["class_name"],
                                    "size_code": ln["size_code"], "copies": 0, "orders": []})
        g["copies"] += int(ln["qty"])
        g["orders"].append(f"{ln['order_no']} x{ln['qty']}")
    files = list(groups.values())
    seen: dict[tuple, int] = {}
    for f in files:
        folder = (f["size_code"], f["copies"])
        name_key = folder + (f["filename"].lower(),)
        if name_key in seen and seen[name_key] != f["photo_id"]:
            stem, ext = posixpath.splitext(f["filename"])
            tag = f["class_name"] or f"p{f['photo_id']}"
            f["filename"] = f"{stem} ({tag}){ext}"
        seen.setdefault(name_key, f["photo_id"])
        f["dest"] = f"{f['size_code']}/{f['copies']}salinan/{f['filename']}"
    return files


def _delivery(ln: dict) -> str:
    if ln["delivery_method"] == "post":
        return f"Pos: {ln['address']}"
    return f"Pickup: {ln['pickup_location']}" if ln["pickup_location"] else "Pickup"


def batch_csv(lines: list[dict], number: int) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Batch", "No. Order", "Nama", "Telefon", "Email", "Sekolah", "Kelas",
                "Nama Fail", "Saiz", "Salinan", "Hantar"])
    for ln in lines:
        w.writerow([number, ln["order_no"], ln["cust_name"], ln["phone_used"] or ln["cust_phone"],
                    ln["cust_email"], ln["school"], ln["class_name"], ln["filename"],
                    ln["size_code"], ln["qty"], _delivery(ln)])
    return ("﻿" + buf.getvalue()).encode("utf-8")   # BOM so Excel reads BM text right


# --- closing a batch ----------------------------------------------------------------
def start_close(conn, batch_id: int, actor: str) -> bool:
    """Mark a batch as closing (new paid orders then open the next batch)."""
    b = one(conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
    if not b or b["status"] != "open":
        return False
    conn.execute("UPDATE batches SET status='closing', closed_at=datetime('now'), error='' WHERE id=?",
                 (batch_id,))
    audit(conn, actor, "batch_close", "event", b["event_id"], f"Batch {b['number']}")
    return True


def arrange(batch_id: int) -> None:
    """Copy the batch's files into its Nextcloud folder + write the batch list.
    Safe to re-run (files are overwritten with the same content)."""
    with db() as conn:
        b = one(conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
        ev = one(conn, "SELECT * FROM events WHERE id=?", (b["event_id"],)) if b else None
        lines = batch_lines(conn, batch_id) if b else []
    if not (b and ev):
        return
    src, dst = settings.nc_instance(ev["nextcloud_id"]), settings.nc_print_instance()
    folder = batch_folder(ev["slug"], b["number"])
    files = plan_files(lines)
    done, errors = 0, []
    if not (src and dst):
        errors.append("Nextcloud not configured")
    else:
        for f in files:
            try:
                data = nextcloud.download(src, f["rel_path"])
                ext = posixpath.splitext(f["filename"])[1].lower()
                nextcloud.upload(dst, f"{folder}/{f['dest']}", data,
                                 CONTENT_TYPES.get(ext, "application/octet-stream"))
                done += 1
            except Exception as exc:  # noqa: BLE001 - keep going, report at the end
                log.exception("batch %s: %s failed", batch_id, f["dest"])
                errors.append(f"{f['dest']}: {type(exc).__name__}")
        try:
            nextcloud.upload(dst, f"{folder}/senarai-batch-{b['number']}.csv",
                             batch_csv(lines, b["number"]), "text/csv")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"senarai csv: {type(exc).__name__}")
    copies = sum(f["copies"] for f in files)
    with db() as conn:
        conn.execute("""UPDATE batches SET status=?, folder=?, n_orders=?, n_files=?, n_copies=?,
                        total_sen=?, error=?, arranged_at=datetime('now') WHERE id=?""",
                     ("closed" if not errors else "error", folder,
                      len({ln["order_id"] for ln in lines}), done, copies,
                      sum(o["total_sen"] for o in batch_orders(conn, batch_id)),
                      "; ".join(errors)[:1000], batch_id))
        if not errors:
            conn.execute("UPDATE orders SET status='printing', updated_at=datetime('now') "
                         "WHERE batch_id=? AND status='paid' AND deleted_at IS NULL", (batch_id,))
        audit(conn, "system", "batch_arranged", "event", ev["id"],
              f"Batch {b['number']}: {done}/{len(files)} file(s), {copies} salinan"
              + (f", {len(errors)} error(s)" if errors else ""))
    write_sheet(ev["id"])


# --- main spreadsheet ---------------------------------------------------------------
def build_sheet(conn, event_id: int) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    ev = one(conn, "SELECT * FROM events WHERE id=?", (event_id,))
    orders = query(conn, """SELECT o.*, c.name cust_name, c.email cust_email, c.phone cust_phone,
                                   b.number batch_no
                            FROM orders o JOIN customers c ON c.id=o.customer_id
                            LEFT JOIN batches b ON b.id=o.batch_id
                            WHERE o.event_id=? AND o.deleted_at IS NULL ORDER BY o.id""", (event_id,))
    batches = query(conn, "SELECT * FROM batches WHERE event_id=? ORDER BY number", (event_id,))
    bold = Font(bold=True)
    wb = Workbook()

    ws = wb.active
    ws.title = "Semua order"
    ws.append([f"{ev['name']} — dikemas kini {local_now():%Y-%m-%d %H:%M}"])
    ws["A1"].font = Font(bold=True, size=13)
    head = ["No. Order", "Tarikh", "Nama", "Email", "Telefon", "Status", "Batch", "Bil. gambar",
            "Salinan", "Subtotal (RM)", "Pos (RM)", "Jumlah (RM)", "Dibayar (RM)", "Hantar"]
    ws.append(head)
    for c in ws[2]:
        c.font = bold
    for o in orders:
        items = query(conn, "SELECT qty FROM order_items WHERE order_id=?", (o["id"],))
        hantar = ("Pos: " + o["address"]) if o["delivery_method"] == "post" else \
            ("Pickup: " + o["pickup_location"] if o["pickup_location"] else "Pickup")
        ws.append([o["order_no"], o["created_at"], o["cust_name"], o["cust_email"],
                   o["phone_used"] or o["cust_phone"], o["status"],
                   f"Batch {o['batch_no']}" if o["batch_no"] else "", len(items),
                   sum(int(i["qty"]) for i in items), o["subtotal_sen"] / 100, o["postage_sen"] / 100,
                   o["total_sen"] / 100, o["paid_sen"] / 100, hantar])
    paid = [o for o in orders if o["status"] in BATCHED_STATUSES]
    ws.append([])
    ws.append(["JUMLAH DIBAYAR", "", "", "", "", f"{len(paid)} order", "", "", "", "", "",
               sum(o["total_sen"] for o in paid) / 100, sum(o["paid_sen"] for o in paid) / 100])
    ws.cell(ws.max_row, 1).font = bold

    wi = wb.create_sheet("Item")
    wi.append(["Batch", "No. Order", "Nama", "Sekolah", "Kelas", "Nama Fail", "Saiz", "Salinan",
               "Harga (RM)", "Jumlah (RM)", "Status"])
    for c in wi[1]:
        c.font = bold
    for o in orders:
        for it in query(conn, "SELECT * FROM order_items WHERE order_id=? ORDER BY id", (o["id"],)):
            wi.append([o["batch_no"] or "", o["order_no"], o["cust_name"], it["school"], it["class_name"],
                       it["filename"], it["size_code"], it["qty"], it["unit_price_sen"] / 100,
                       it["qty"] * it["unit_price_sen"] / 100, o["status"]])

    wb_ = wb.create_sheet("Ringkasan batch")
    wb_.append(["Batch", "Status", "Dibuka", "Ditutup", "Order", "Fail", "Salinan", "Jumlah (RM)",
                "Folder"])
    for c in wb_[1]:
        c.font = bold
    for b in batches:
        b_orders = batch_orders(conn, b["id"])
        n_copies = b["n_copies"] or sum(
            int(r["qty"]) for r in query(conn, "SELECT i.qty FROM order_items i JOIN orders o ON o.id=i.order_id "
                                               "WHERE o.batch_id=? AND o.deleted_at IS NULL", (b["id"],)))
        wb_.append([f"Batch {b['number']}", b["status"], b["opened_at"], b["closed_at"] or "",
                    len(b_orders), b["n_files"] or "", n_copies,
                    sum(o["total_sen"] for o in b_orders) / 100, b["folder"] or ""])
    for sheet in (ws, wi, wb_):
        for col in sheet.columns:
            width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            sheet.column_dimensions[col[0].column_letter].width = min(max(width + 2, 8), 45)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def write_sheet(event_id: int) -> None:
    """Rewrite the event's main spreadsheet in Nextcloud (best effort)."""
    try:
        with db() as conn:
            ev = one(conn, "SELECT slug FROM events WHERE id=?", (event_id,))
            data = build_sheet(conn, event_id)
        dst = settings.nc_print_instance()
        if ev and dst:
            nextcloud.upload(dst, sheet_path(ev["slug"]), data,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception:  # noqa: BLE001
        log.exception("main spreadsheet not written for event %s", event_id)


def summary(conn, event_id: int) -> dict:
    """What the admin event page shows: open batch figures + closed batches."""
    ev = one(conn, "SELECT slug FROM events WHERE id=?", (event_id,))
    rows = query(conn, "SELECT * FROM batches WHERE event_id=? ORDER BY number DESC", (event_id,))
    out = []
    for b in rows:
        lines = batch_lines(conn, b["id"])
        files = plan_files(lines)
        out.append({**dict(b), "orders": len({ln["order_id"] for ln in lines}), "files": len(files),
                    "copies": sum(f["copies"] for f in files),
                    "total": rm(sum(o["total_sen"] for o in batch_orders(conn, b["id"]))),
                    "link": files_link(b["folder"] or batch_folder(ev["slug"], b["number"]))})
    return {"batches": out, "event_link": files_link(event_folder(ev["slug"])) if ev else ""}
