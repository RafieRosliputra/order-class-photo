"""Customer order views: list + single order (status, items, payment, receipts)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from .. import duitnow
from ..database import db, one, query
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
    balance = max(0, order["total_sen"] - order["paid_sen"])
    overpaid = order["paid_sen"] > order["total_sen"]
    return render(request, "order.html", {
        "order": order, "event": event, "items": items, "receipts": receipts,
        "balance_sen": balance, "overpaid": overpaid, "status_flow": STATUS_FLOW,
        "duitnow_on": duitnow.is_configured(),
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
