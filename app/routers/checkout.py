"""Checkout: delivery choice, address/map, then create the order."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ..database import db, one, query
from ..deps import (cart_event_id, current_customer, read_cart, render, write_cart)
from ..orders_service import create_order_from_cart
from ..pricing import cart_subtotal

router = APIRouter()


@router.get("/checkout")
def checkout_page(request: Request):
    cart = read_cart(request)
    event_id = cart_event_id(cart)
    if not event_id:
        return RedirectResponse("/cart", status_code=303)
    customer = current_customer(request)
    if not customer:
        return RedirectResponse("/login?next=/checkout", status_code=303)

    with db() as conn:
        event = one(conn, "SELECT * FROM events WHERE id=?", (event_id,))
        subtotal = cart_subtotal(conn, cart)
        schools = [r["school"] for r in query(
            conn, "SELECT DISTINCT school FROM classes WHERE event_id=? AND school!='' ORDER BY school",
            (event_id,))]
    return render(request, "checkout.html", {
        "event": event, "subtotal_sen": subtotal, "customer": customer, "schools": schools,
    })


@router.post("/checkout")
def checkout_submit(
    request: Request,
    delivery: str = Form("pickup"),
    zone: str = Form("west"),
    address: str = Form(""),
    lat: str = Form(""),
    lng: str = Form(""),
    name: str = Form(""),
    phone: str = Form(""),
    category: str = Form(""),
):
    cart = read_cart(request)
    event_id = cart_event_id(cart)
    if not event_id or not cart:
        return RedirectResponse("/cart", status_code=303)
    customer = current_customer(request)
    if not customer:
        return RedirectResponse("/login?next=/checkout", status_code=303)

    delivery = "post" if delivery == "post" else "pickup"
    if delivery == "post" and not address.strip():
        with db() as conn:
            event = one(conn, "SELECT * FROM events WHERE id=?", (event_id,))
            subtotal = cart_subtotal(conn, cart)
        return render(request, "checkout.html", {
            "event": event, "subtotal_sen": subtotal, "customer": customer,
            "error": "address_required", "schools": [],
        })

    phone = phone.strip()
    with db() as conn:
        # update customer name / phone (phone change is logged; admin notified via audit)
        if phone and phone != customer["phone"]:
            history = json.loads(customer["phone_history"] or "[]")
            history.append({"phone": phone, "at": datetime.now(timezone.utc).isoformat()})
            conn.execute("UPDATE customers SET phone=?, phone_history=? WHERE id=?",
                         (phone, json.dumps(history), customer["id"]))
            conn.execute(
                "INSERT INTO audit_log(actor, action, entity, entity_id, detail) VALUES (?,?,?,?,?)",
                (f"customer:{customer['id']}", "phone_changed", "customer", customer["id"], phone))
        if name.strip():
            conn.execute("UPDATE customers SET name=? WHERE id=?", (name.strip(), customer["id"]))

        latf = float(lat) if lat.strip() else None
        lngf = float(lng) if lng.strip() else None
        order_id = create_order_from_cart(
            conn, event_id, customer["id"], cart,
            delivery=delivery, address=address.strip(), lat=latf, lng=lngf,
            zone=("east" if zone == "east" else "west"),
            category=category.strip(), phone=phone or customer["phone"],
        )
        order = one(conn, "SELECT order_no FROM orders WHERE id=?", (order_id,))

    resp = RedirectResponse(f"/order/{order['order_no']}", status_code=303)
    write_cart(resp, {})  # cart consumed
    return resp
