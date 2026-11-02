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


def parse_cart_key(key: str) -> tuple[int, int, int] | None:
    """Cart keys are 'event_id:photo_id:size_id'; size_id 0 = size not chosen yet."""
    parts = key.split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def cart_unsized(cart: dict) -> int:
    """How many cart photos still have no print size."""
    return sum(1 for k in cart if (p := parse_cart_key(k)) and p[2] == 0)


def cart_subtotal(conn, cart: dict) -> int:
    """Sum of sized cart lines, in sen (lines without a size count as 0)."""
    total = 0
    for key, qty in cart.items():
        parsed = parse_cart_key(key)
        if not parsed or parsed[2] == 0:
            continue
        total += size_price(conn, parsed[2]) * int(qty)
    return total
