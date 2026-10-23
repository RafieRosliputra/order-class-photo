from app.database import db, one
from app.orders_service import _reconcile_payment, create_order_from_cart


def _setup_event(conn):
    eid = conn.execute(
        "INSERT INTO events(slug,name,nextcloud_folder) VALUES ('e','E','f')").lastrowid
    sid = conn.execute(
        "INSERT INTO sizes(event_id,code,label,price_sen,sort) VALUES (?,?,?,?,0)",
        (eid, "4R", "4x6", 500)).lastrowid
    cid = conn.execute(
        "INSERT INTO classes(event_id,school,name,folder_path) VALUES (?,?,?,?)",
        (eid, "SKA", "6 Bestari", "f/SKA - 6 Bestari")).lastrowid
    pid = conn.execute(
        "INSERT INTO photos(event_id,class_id,filename,rel_path) VALUES (?,?,?,?)",
        (eid, cid, "DSC_0001.jpg", "f/SKA - 6 Bestari/DSC_0001.jpg")).lastrowid
    cust = conn.execute("INSERT INTO customers(email,phone) VALUES ('a@b.com','0120000000')").lastrowid
    return eid, sid, pid, cust


def test_order_totals_and_exact_payment():
    with db() as conn:
        eid, sid, pid, cust = _setup_event(conn)
        cart = {f"{eid}:{pid}:{sid}": 3}   # 3 × RM5 = RM15
        oid = create_order_from_cart(conn, eid, cust, cart, delivery="pickup",
                                     address="", lat=None, lng=None, zone="west",
                                     category="", phone="0120000000")
        order = one(conn, "SELECT * FROM orders WHERE id=?", (oid,))
        assert order["subtotal_sen"] == 1500
        assert order["total_sen"] == 1500

        # exact payment -> paid
        conn.execute("INSERT INTO receipts(order_id,customer_id,amount_sen,ocr_status,accepted) "
                     "VALUES (?,?,?,?,1)", (oid, cust, 1500, "ok"))
        state = _reconcile_payment(conn, oid)
        assert state["status"] == "paid"
        assert state["balance_sen"] == 0


def test_partial_then_balance():
    with db() as conn:
        eid, sid, pid, cust = _setup_event(conn)
        cart = {f"{eid}:{pid}:{sid}": 4}   # RM20
        oid = create_order_from_cart(conn, eid, cust, cart, delivery="pickup",
                                     address="", lat=None, lng=None, zone="west",
                                     category="", phone="x")
        conn.execute("INSERT INTO receipts(order_id,customer_id,amount_sen,ocr_status,accepted) "
                     "VALUES (?,?,?,?,1)", (oid, cust, 1500, "ok"))
        s1 = _reconcile_payment(conn, oid)
        assert s1["status"] == "reviewing"
        assert s1["balance_sen"] == 500
        conn.execute("INSERT INTO receipts(order_id,customer_id,amount_sen,ocr_status,accepted) "
                     "VALUES (?,?,?,?,1)", (oid, cust, 500, "ok"))
        s2 = _reconcile_payment(conn, oid)
        assert s2["status"] == "paid"


def test_postage_east():
    with db() as conn:
        eid, sid, pid, cust = _setup_event(conn)
        conn.execute("UPDATE events SET postage_east_sen=1800 WHERE id=?", (eid,))
        cart = {f"{eid}:{pid}:{sid}": 1}
        oid = create_order_from_cart(conn, eid, cust, cart, delivery="post",
                                     address="Sabah", lat=None, lng=None, zone="east",
                                     category="", phone="x")
        order = one(conn, "SELECT * FROM orders WHERE id=?", (oid,))
        assert order["postage_sen"] == 1800
        assert order["total_sen"] == 500 + 1800
