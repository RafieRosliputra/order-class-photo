"""Cart: add from gallery, change size/qty in the cart page. Cart lives in a
signed cookie (one event at a time) and survives until login/checkout."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..database import db, one, query
from ..deps import cart_count, cart_event_id, read_cart, render, write_cart
from ..pricing import cart_subtotal

router = APIRouter()


def _default_size_id(conn, event_id: int) -> int | None:
    row = one(conn, "SELECT id FROM sizes WHERE event_id=? ORDER BY sort, price_sen LIMIT 1",
              (event_id,))
    return row["id"] if row else None


@router.post("/cart/add")
async def cart_add(request: Request):
    body = await request.json()
    event_id = int(body.get("event_id"))
    photo_ids = [int(p) for p in body.get("photo_ids", [])]
    cart = read_cart(request)

    # cart is scoped to a single event
    if cart_event_id(cart) not in (None, event_id):
        cart = {}

    with db() as conn:
        size_id = _default_size_id(conn, event_id)
        if not size_id:
            return JSONResponse({"error": "no_sizes"}, status_code=400)
        valid = {r["id"] for r in query(
            conn, "SELECT id FROM photos WHERE event_id=? AND id IN (%s)" %
            (",".join("?" * len(photo_ids)) or "NULL"), [event_id, *photo_ids])} if photo_ids else set()
    added = 0
    for pid in photo_ids:
        if pid not in valid:
            continue
        key = f"{event_id}:{pid}:{size_id}"
        if key not in cart:
            cart[key] = 1
            added += 1
    resp = JSONResponse({"count": cart_count(cart), "added": added})
    write_cart(resp, cart)
    return resp


@router.post("/cart/update")
def cart_update(request: Request, key: str = Form(...), qty: int = Form(...)):
    cart = read_cart(request)
    if qty <= 0:
        cart.pop(key, None)
    else:
        cart[key] = min(qty, 20)
    resp = RedirectResponse("/cart", status_code=303)
    write_cart(resp, cart)
    return resp


@router.post("/cart/change-size")
def cart_change_size(request: Request, key: str = Form(...), size_id: int = Form(...)):
    cart = read_cart(request)
    qty = cart.pop(key, 1)
    try:
        ev, pid, _ = key.split(":")
    except ValueError:
        return RedirectResponse("/cart", status_code=303)
    newkey = f"{ev}:{pid}:{size_id}"
    cart[newkey] = min(cart.get(newkey, 0) + qty, 20)
    resp = RedirectResponse("/cart", status_code=303)
    write_cart(resp, cart)
    return resp


@router.post("/cart/add-size")
def cart_add_size(request: Request, event_id: int = Form(...), photo_id: int = Form(...),
                  size_id: int = Form(...)):
    cart = read_cart(request)
    key = f"{event_id}:{photo_id}:{size_id}"
    cart[key] = min(cart.get(key, 0) + 1, 20)
    resp = RedirectResponse("/cart", status_code=303)
    write_cart(resp, cart)
    return resp


@router.post("/cart/clear")
def cart_clear(request: Request):
    resp = RedirectResponse("/cart", status_code=303)
    write_cart(resp, {})
    return resp


@router.get("/cart")
def cart_page(request: Request):
    cart = read_cart(request)
    event_id = cart_event_id(cart)
    items, event, sizes, subtotal = [], None, [], 0
    if event_id:
        with db() as conn:
            event = one(conn, "SELECT * FROM events WHERE id=?", (event_id,))
            sizes = query(conn, "SELECT * FROM sizes WHERE event_id=? ORDER BY sort, price_sen",
                          (event_id,))
            for key, qty in cart.items():
                parts = key.split(":")
                if len(parts) != 3:
                    continue
                _, pid, sid = parts
                photo = one(conn, "SELECT * FROM photos WHERE id=?", (pid,))
                size = one(conn, "SELECT * FROM sizes WHERE id=?", (sid,))
                if not (photo and size):
                    continue
                items.append({
                    "key": key, "photo": photo, "size": size, "qty": qty,
                    "line_sen": qty * size["price_sen"],
                })
            subtotal = cart_subtotal(conn, cart)
    return render(request, "cart.html", {
        "items": items, "event": event, "sizes": sizes, "subtotal_sen": subtotal,
    })
