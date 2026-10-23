"""Order total calculation. All amounts in sen."""
from __future__ import annotations

from .database import one, query


def size_price(conn, size_id: int) -> int:
    row = one(conn, "SELECT price_sen FROM sizes WHERE id=?", (size_id,))
    return int(row["price_sen"]) if row else 0


def postage_for(conn, event_id: int, method: str, zone: str = "west") -> int:
    if method != "post":
        return 0
    ev = one(conn, "SELECT postage_west_sen, postage_east_sen FROM events WHERE id=?", (event_id,))
    if not ev:
        return 0
    return int(ev["postage_east_sen"] if zone == "east" else ev["postage_west_sen"])


def compute_order_totals(conn, order_id: int) -> dict:
    """Recompute subtotal/total from items + postage and persist them."""
    items = query(
        conn,
        "SELECT qty, unit_price_sen FROM order_items WHERE order_id=?",
        (order_id,),
    )
    subtotal = sum(int(i["qty"]) * int(i["unit_price_sen"]) for i in items)
    order = one(conn, "SELECT postage_sen FROM orders WHERE id=?", (order_id,))
    postage = int(order["postage_sen"]) if order else 0
    total = subtotal + postage
    conn.execute(
        "UPDATE orders SET subtotal_sen=?, total_sen=?, updated_at=datetime('now') WHERE id=?",
        (subtotal, total, order_id),
    )
    return {"subtotal_sen": subtotal, "postage_sen": postage, "total_sen": total}


def cart_subtotal(conn, cart: dict) -> int:
    """cart = {"photo_id:size_id": qty}. Returns sen."""
    total = 0
    for key, qty in cart.items():
        try:
            _, size_id = key.split(":")
        except ValueError:
            continue
        total += size_price(conn, int(size_id)) * int(qty)
    return total
