"""Cart: add from gallery, change size/qty in the cart page. Cart lives in a
signed cookie (one event at a time) and survives until login/checkout."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .. import event_access
from ..database import db, one, query
from ..deps import cart_count, cart_event_id, read_cart, render, write_cart
from ..pricing import cart_subtotal, cart_unsized, parse_cart_key

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
        event = one(conn, "SELECT * FROM events WHERE id=?", (event_id,))
        if not event or not event_access.has_access(request, event):
            return JSONResponse({"error": "gallery_locked"}, status_code=403)
        if not _default_size_id(conn, event_id):
            return JSONResponse({"error": "no_sizes"}, status_code=400)
        valid = {r["id"] for r in query(
            conn, "SELECT id FROM photos WHERE event_id=? AND id IN (%s)" %
            (",".join("?" * len(photo_ids)) or "NULL"), [event_id, *photo_ids])} if photo_ids else set()
    added = 0
    in_cart = {p[1] for k in cart if (p := parse_cart_key(k))}
    for pid in photo_ids:
        if pid not in valid or pid in in_cart:
            continue
        # no size yet: the customer picks one in the cart (price shows only then)
        cart[f"{event_id}:{pid}:0"] = 1
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
    parsed = parse_cart_key(key)
    if not parsed or key not in cart:
        return RedirectResponse("/cart", status_code=303)
    ev, pid, _ = parsed
    newkey = f"{ev}:{pid}:{size_id}"
    if newkey != key:
        qty = cart.pop(key, 1)
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
    unsized = cart_unsized(cart)
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
                size = one(conn, "SELECT * FROM sizes WHERE id=?", (sid,)) if sid != "0" else None
                if not photo:
                    continue
                items.append({
                    "key": key, "photo": photo, "size": size, "qty": qty,
                    "line_sen": qty * size["price_sen"] if size else 0,
                })
            # keep each photo's lines together, in gallery order
            items.sort(key=lambda it: (it["photo"]["filename"], it["size"]["sort"] if it["size"] else -1))
            subtotal = cart_subtotal(conn, cart)
    return render(request, "cart.html", {
        "items": items, "event": event, "sizes": sizes, "subtotal_sen": subtotal,
        "unsized": unsized, "sized_count": len(items) - unsized,
    })
