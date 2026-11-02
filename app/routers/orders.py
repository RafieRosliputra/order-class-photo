"""Customer order views: list + single order (status, items, payment, receipts)."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response

from .. import duitnow
from ..database import audit, db, one, query
from ..pricing import compute_order_totals
from ..deps import current_customer, render
from ..utils import STATUS_FLOW

router = APIRouter()


@router.get("/orders")
def my_orders(request: Request):
    customer = current_customer(request)
    if not customer:
        return RedirectResponse("/login?next=/orders", status_code=303)
    with db() as conn:
        orders = query(
            conn,
            """SELECT o.*, e.name AS event_name, e.slug AS event_slug
               FROM orders o JOIN events e ON e.id=o.event_id
               WHERE o.customer_id=? ORDER BY o.created_at DESC""",
            (customer["id"],),
        )
    return render(request, "orders.html", {"orders": orders})


@router.get("/order/{order_no}")
def order_detail(order_no: str, request: Request):
    customer = current_customer(request)
    if not customer:
        return RedirectResponse(f"/login?next=/order/{order_no}", status_code=303)
    with db() as conn:
        order = one(conn, "SELECT * FROM orders WHERE order_no=?", (order_no,))
        if not order or order["customer_id"] != customer["id"]:
            return render(request, "not_found.html", {})
        event = one(conn, "SELECT * FROM events WHERE id=?", (order["event_id"],))
        items = query(conn, "SELECT * FROM order_items WHERE order_id=?", (order["id"],))
        receipts = query(conn, "SELECT * FROM receipts WHERE order_id=? ORDER BY created_at",
                         (order["id"],))
        sizes = query(conn, "SELECT * FROM sizes WHERE event_id=? ORDER BY sort, price_sen",
                      (order["event_id"],))
        editable = _editable(conn, order)
    balance = max(0, order["total_sen"] - order["paid_sen"])
    overpaid = order["paid_sen"] > order["total_sen"]
    return render(request, "order.html", {
        "order": order, "event": event, "items": items, "receipts": receipts,
        "balance_sen": balance, "overpaid": overpaid, "status_flow": STATUS_FLOW,
        "duitnow_on": duitnow.is_configured(), "sizes": sizes, "editable": editable,
    })


@router.get("/order/{order_no}/qr.png")
def order_qr(order_no: str, request: Request):
    """Per-order dynamic DuitNow QR (amount + phone reference embedded)."""
    customer = current_customer(request)
    if not customer:
        return Response(status_code=403)
    if not duitnow.is_configured():
        return Response(status_code=404)
    with db() as conn:
        order = one(conn, "SELECT * FROM orders WHERE order_no=?", (order_no,))
    if not order or order["customer_id"] != customer["id"]:
        return Response(status_code=404)
    try:
        png = duitnow.qr_for_order_png(order["total_sen"], order["phone_used"] or customer["phone"])
    except Exception:  # noqa: BLE001 - never 500 the pay page over a QR
        return Response(status_code=404)
    return Response(png, media_type="image/png",
                    headers={"Cache-Control": "private, no-store"})


# --- edit an order before any receipt is sent -------------------------------
def _editable(conn, order) -> bool:
    """Items may change only while awaiting payment and before any receipt."""
    if order["status"] != "awaiting_payment":
        return False
    return not one(conn, "SELECT 1 FROM receipts WHERE order_id=?", (order["id"],))


def _own_editable_order(conn, request: Request, order_no: str):
    customer = current_customer(request)
    if not customer:
        return None, None
    order = one(conn, "SELECT * FROM orders WHERE order_no=?", (order_no,))
    if not order or order["customer_id"] != customer["id"] or not _editable(conn, order):
        return None, customer
    return order, customer


def _back(order_no: str, flag: str = "") -> RedirectResponse:
    return RedirectResponse(f"/order/{order_no}{('?' + flag + '#items') if flag else ''}", status_code=303)


@router.post("/order/{order_no}/items/{item_id}/qty")
def order_item_qty(order_no: str, item_id: int, request: Request, qty: int = Form(...)):
    with db() as conn:
        order, customer = _own_editable_order(conn, request, order_no)
        if not order:
            return _back(order_no, "locked=1")
        item = one(conn, "SELECT * FROM order_items WHERE id=? AND order_id=?", (item_id, order["id"]))
        if item:
            conn.execute("UPDATE order_items SET qty=? WHERE id=?", (max(1, min(qty, 20)), item_id))
            compute_order_totals(conn, order["id"])
            audit(conn, f"customer:{customer['id']}", "order_item_qty", "order", order["id"], f"{item_id}->{qty}")
    return _back(order_no)


@router.post("/order/{order_no}/items/{item_id}/size")
def order_item_size(order_no: str, item_id: int, request: Request, size_id: int = Form(...)):
    with db() as conn:
        order, customer = _own_editable_order(conn, request, order_no)
        if not order:
            return _back(order_no, "locked=1")
        item = one(conn, "SELECT * FROM order_items WHERE id=? AND order_id=?", (item_id, order["id"]))
        size = one(conn, "SELECT * FROM sizes WHERE id=? AND event_id=?", (size_id, order["event_id"]))
        if item and size and item["size_id"] != size["id"]:
            twin = one(conn, "SELECT * FROM order_items WHERE order_id=? AND photo_id=? AND size_id=? AND id!=?",
                       (order["id"], item["photo_id"], size["id"], item_id))
            if twin:  # same photo already in that size: merge the copies
                conn.execute("UPDATE order_items SET qty=? WHERE id=?",
                             (min(twin["qty"] + item["qty"], 20), twin["id"]))
                conn.execute("DELETE FROM order_items WHERE id=?", (item_id,))
            else:
                conn.execute("UPDATE order_items SET size_id=?, unit_price_sen=?, size_code=? WHERE id=?",
                             (size["id"], size["price_sen"], size["code"], item_id))
            compute_order_totals(conn, order["id"])
            audit(conn, f"customer:{customer['id']}", "order_item_size", "order", order["id"], f"{item_id}->{size['code']}")
    return _back(order_no)


@router.post("/order/{order_no}/items/{item_id}/remove")
def order_item_remove(order_no: str, item_id: int, request: Request):
    with db() as conn:
        order, customer = _own_editable_order(conn, request, order_no)
        if not order:
            return _back(order_no, "locked=1")
        n = one(conn, "SELECT COUNT(*) c FROM order_items WHERE order_id=?", (order["id"],))["c"]
        if n <= 1:  # an order needs at least one photo; cancel via WhatsApp instead
            return _back(order_no, "last_item=1")
        conn.execute("DELETE FROM order_items WHERE id=? AND order_id=?", (item_id, order["id"]))
        compute_order_totals(conn, order["id"])
        audit(conn, f"customer:{customer['id']}", "order_item_removed", "order", order["id"], str(item_id))
    return _back(order_no)
