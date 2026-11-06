"""Receipt OCR decisions, stuck-receipt rescan, soft delete and order numbers."""
import io

from PIL import Image, ImageDraw, ImageFont

from app import ocr, orders_service
from app.database import db, get_setting, one, set_setting
from app.utils import next_order_no
from tests.test_orders import _setup_event


def _order(conn, qty=1):
    eid, sid, pid, cust = _setup_event(conn)          # 1 x RM5 per qty
    oid = orders_service.create_order_from_cart(
        conn, eid, cust, {f"{eid}:{pid}:{sid}": qty}, delivery="pickup", address="",
        lat=None, lng=None, zone="west", category="", phone="0120000000")
    return oid, cust


def _fake_ocr(monkeypatch, result):
    monkeypatch.setattr(orders_service, "_ocr_bytes", lambda conn, data, mime: dict(result))


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), "white").save(buf, "PNG")
    return buf.getvalue()


def _good(amount_sen, ref="7712345678"):
    return {"ok": True, "amount_sen": amount_sen, "receipt_no": ref, "receipt_date": "",
            "receipt_time": "", "bank": "Maybank", "raw": "x", "is_receipt": True,
            "txn_status": "successful", "engine": "tesseract+deepseek"}


def test_exact_match_marks_paid(monkeypatch):
    _fake_ocr(monkeypatch, _good(500))
    with db() as conn:
        oid, cust = _order(conn)
        st = orders_service.process_receipt(conn, oid, cust, _png(), "r.png", "image/png")
        r = one(conn, "SELECT * FROM receipts WHERE order_id=?", (oid,))
    assert st["status"] == "paid" and st["just_paid"]
    assert r["ocr_note"] == "match" and r["accepted"] == 1


def test_unreadable_receipt_moves_to_reviewing(monkeypatch):
    """The live bug: OCR failed and the order stayed 'awaiting_payment'."""
    _fake_ocr(monkeypatch, {"ok": False, "reason": "ModuleNotFoundError", "engine": ""})
    with db() as conn:
        oid, cust = _order(conn)
        st = orders_service.process_receipt(conn, oid, cust, _png(), "r.png", "image/png")
        r = one(conn, "SELECT * FROM receipts WHERE order_id=?", (oid,))
    assert st["status"] == "reviewing"
    assert r["ocr_note"] == "unreadable" and r["accepted"] == 0


def test_partial_and_failed_txn(monkeypatch):
    _fake_ocr(monkeypatch, _good(300))
    with db() as conn:
        oid, cust = _order(conn)
        st = orders_service.process_receipt(conn, oid, cust, _png(), "r.png", "image/png")
    assert st["status"] == "reviewing" and st["balance_sen"] == 200
    res = _good(500, ref="X99999999"); res["txn_status"] = "failed"
    _fake_ocr(monkeypatch, res)
    with db() as conn:
        oid2 = orders_service.create_order_from_cart(
            conn, 1, cust, {"1:1:1": 1}, delivery="pickup", address="", lat=None, lng=None,
            zone="west", category="", phone="1")
        st = orders_service.process_receipt(conn, oid2, cust, _png(), "r.png", "image/png")
        r = one(conn, "SELECT * FROM receipts WHERE order_id=?", (oid2,))
    assert st["status"] == "reviewing" and r["ocr_note"] == "failed_txn"


def test_rescan_fixes_stuck_receipt(monkeypatch):
    _fake_ocr(monkeypatch, {"ok": False, "reason": "no paddle", "engine": ""})
    with db() as conn:
        oid, cust = _order(conn)
        orders_service.process_receipt(conn, oid, cust, _png(), "r.png", "image/png")
        # simulate an old receipt never checked by the new OCR
        conn.execute("UPDATE receipts SET ocr_checked_at=NULL")
        conn.execute("UPDATE orders SET status='awaiting_payment'")
    sent = []
    monkeypatch.setattr(orders_service, "finalize_payment", lambda oid: None)
    monkeypatch.setattr(orders_service, "send_admin_notice", lambda *a: sent.append(a[1]))
    _fake_ocr(monkeypatch, _good(500))
    assert orders_service.rescan_pending() == 1
    with db() as conn:
        o = one(conn, "SELECT * FROM orders WHERE id=?", (oid,))
    assert o["status"] == "paid" and o["paid_sen"] == 500
    assert sent == ["paid"]


def test_ai_amount_must_appear_in_text():
    parsed = ocr.parse_text("Transfer successful\nAmount RM 4.00\nRef 123456789")
    out = ocr.merge_ai(parsed, {"is_receipt": True, "status": "successful", "amount": "40.00"})
    assert out["amount_sen"] == 400          # invented 40.00 ignored
    out = ocr.merge_ai(parsed, {"is_receipt": True, "status": "successful", "amount": "4.00",
                                "reference": "abc123456"})
    assert out["amount_sen"] == 400 and out["receipt_no"] == "ABC123456"


def test_tesseract_reads_a_receipt_image(tmp_path):
    img = Image.new("RGB", (900, 500), "white")
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("DejaVuSans.ttf", 36)
    except OSError:
        f = ImageFont.load_default()
    for i, line in enumerate(["Maybank2u", "Transfer Successful", "Amount RM 4.00",
                              "Reference No 7712345678", "Date 06/11/2026 10:21"]):
        d.text((40, 30 + i * 80), line, fill="black", font=f)
    p = tmp_path / "r.png"; img.save(p)
    res = ocr.run_ocr(str(p), {"key": ""})
    assert res["ok"] and res["engine"] == "tesseract"
    assert res["amount_sen"] == 400 and res["receipt_no"] == "7712345678"


def test_settings_roundtrip():
    with db() as conn:
        set_setting(conn, "deepseek_api_key", "sk-1")
        set_setting(conn, "deepseek_api_key", "sk-2")
        assert get_setting(conn, "deepseek_api_key") == "sk-2"
        assert ocr.ai_config(conn)["key"] == "sk-2"


def test_order_no_never_reused_after_purge():
    with db() as conn:
        _order(conn)
        oid2 = orders_service.create_order_from_cart(
            conn, 1, 1, {"1:1:1": 1}, delivery="pickup", address="", lat=None, lng=None,
            zone="west", category="", phone="1")
        no2 = one(conn, "SELECT order_no FROM orders WHERE id=?", (oid2,))["order_no"]
        conn.execute("DELETE FROM orders WHERE order_no LIKE '%-001'")
        assert next_order_no(conn) != no2 and next_order_no(conn).endswith("-003")


def test_deleted_orders_are_not_rescanned(monkeypatch):
    _fake_ocr(monkeypatch, {"ok": False, "reason": "x", "engine": ""})
    with db() as conn:
        oid, cust = _order(conn)
        orders_service.process_receipt(conn, oid, cust, _png(), "r.png", "image/png")
        conn.execute("UPDATE orders SET deleted_at=datetime('now') WHERE id=?", (oid,))
        assert orders_service.pending_receipt_ids(conn) == []


def test_tng_duitnow_ref_with_dot():
    p = ocr.parse_text("RM 4.00\nPaid\nDuitNow Ref No. 20261106TNGDMYNBO300\nDate/Time 06/11/2026 12:41:10")
    assert p["receipt_no"] == "20261106TNGDMYNBO300" and p["amount_sen"] == 400


def test_same_receipt_twice_counts_once(monkeypatch):
    res = _good(500, ref=""); res["raw"] = "RM 5.00 Paid same text"
    _fake_ocr(monkeypatch, res)
    with db() as conn:
        oid, cust = _order(conn)
        orders_service.process_receipt(conn, oid, cust, _png(), "a.png", "image/png")
        st = orders_service.process_receipt(conn, oid, cust, _png(), "b.png", "image/png", forced=True)
        rows = [dict(r) for r in conn.execute("SELECT accepted, ocr_note FROM receipts WHERE order_id=? ORDER BY id", (oid,))]
    assert st["paid_sen"] == 500 and st["status"] == "paid"
    assert rows[1] == {"accepted": 0, "ocr_note": "duplicate"}


def test_rerun_first_copy_is_not_duplicate_of_later_copy(monkeypatch):
    res = _good(500, ref="REF12345678")
    _fake_ocr(monkeypatch, res)
    with db() as conn:
        oid, cust = _order(conn)
        orders_service.process_receipt(conn, oid, cust, _png(), "a.png", "image/png")
        orders_service.process_receipt(conn, oid, cust, _png(), "b.png", "image/png", forced=True)
        ids = [r["id"] for r in conn.execute("SELECT id FROM receipts WHERE order_id=? ORDER BY id", (oid,))]
        orders_service.rerun_receipt(conn, ids[1])
        st = orders_service.rerun_receipt(conn, ids[0])
        notes = [r["ocr_note"] for r in conn.execute("SELECT ocr_note FROM receipts ORDER BY id")]
    assert notes == ["match", "duplicate"] and st["paid_sen"] == 500


def test_vision_amount_not_in_text_goes_to_review(monkeypatch):
    parsed = ocr.parse_text("blurry")
    out = ocr.merge_ai(parsed, {"is_receipt": True, "status": "successful", "amount": "5.00", "_vision": True})
    assert out["amount_sen"] == 500 and out["amount_verified"] is False
    _fake_ocr(monkeypatch, out | {"ok": True, "engine": "deepseek-vision"})
    with db() as conn:
        oid, cust = _order(conn)
        st = orders_service.process_receipt(conn, oid, cust, _png(), "r.png", "image/png")
        r = one(conn, "SELECT * FROM receipts WHERE order_id=?", (oid,))
    assert st["status"] == "reviewing" and r["ocr_note"] == "unverified" and r["amount_sen"] == 500


def test_ai_parse_sends_image_and_retries_without_json_mode(monkeypatch, tmp_path):
    img = tmp_path / "r.png"; Image.new("RGB", (50, 50), "white").save(img)
    calls = []

    class Resp:
        def __init__(self, code, content=""):
            self.status_code, self._c = code, content
        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)
        def json(self):
            return {"choices": [{"message": {"content": self._c}}]}

    def fake_post(url, json, timeout, headers):
        calls.append(json)
        if "response_format" in json:
            return Resp(400)
        return Resp(200, 'Here: {"is_receipt": true, "status": "successful", "amount": "4.00"}')

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post, raising=False)
    data = ocr.ai_parse("RM 4.00", {"key": "k", "base_url": "https://api.deepseek.com", "model": "deepseek-flash"}, img)
    user = calls[0]["messages"][1]["content"]
    assert calls[0]["model"] == "deepseek-flash"
    assert user[1]["type"] == "image_url" and user[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert len(calls) == 2 and data["amount"] == "4.00" and data["_vision"] is True


def test_reject_sends_order_back_to_awaiting_payment(monkeypatch):
    _fake_ocr(monkeypatch, _good(300))                       # RM3 on a RM5 order
    with db() as conn:
        oid, cust = _order(conn)
        orders_service.process_receipt(conn, oid, cust, _png(), "r.png", "image/png")
        rid = one(conn, "SELECT id FROM receipts WHERE order_id=?", (oid,))["id"]
        st = orders_service.reject_receipt(conn, rid, "Amaun RM3, order RM5", "admin@x")
        r = one(conn, "SELECT * FROM receipts WHERE id=?", (rid,))
        o = one(conn, "SELECT * FROM orders WHERE id=?", (oid,))
        assert st["status"] == "awaiting_payment" and o["paid_sen"] == 0
        assert r["rejected"] == 1 and r["accepted"] == 0 and r["reject_reason"] == "Amaun RM3, order RM5"
        # rejected receipts don't lock editing and are never re-scanned or revived


def test_rejected_receipt_stays_rejected_after_rerun(monkeypatch):
    _fake_ocr(monkeypatch, _good(300, ref="R1234567"))
    with db() as conn:
        oid, cust = _order(conn)
        orders_service.process_receipt(conn, oid, cust, _png(), "r.png", "image/png")
        rid = one(conn, "SELECT id FROM receipts WHERE order_id=?", (oid,))["id"]
        orders_service.reject_receipt(conn, rid, "x", "admin")
        assert orders_service.pending_receipt_ids(conn) == []
        _fake_ocr(monkeypatch, _good(500, ref="R1234567"))
        orders_service.rerun_receipt(conn, rid)
        assert one(conn, "SELECT accepted FROM receipts WHERE id=?", (rid,))["accepted"] == 0
        assert one(conn, "SELECT status FROM orders WHERE id=?", (oid,))["status"] == "awaiting_payment"


def test_refund_and_paid_amount_kept(monkeypatch):
    _fake_ocr(monkeypatch, _good(800))                       # RM8 on a RM5 order
    with db() as conn:
        oid, cust = _order(conn)
        st = orders_service.process_receipt(conn, oid, cust, _png(), "r.png", "image/png")
        assert st["status"] == "reviewing" and st["overpaid"]
        conn.execute("UPDATE orders SET status='paid', paid_sen=MAX(paid_sen,total_sen) WHERE id=?", (oid,))
        assert orders_service.mark_refunded(conn, oid, "admin") == 300
        o = one(conn, "SELECT * FROM orders WHERE id=?", (oid,))
        assert o["refunded_sen"] == 300 and o["refunded_at"]
        # a later recompute never lowers an admin-confirmed paid amount
        orders_service._reconcile_payment(conn, oid)
        assert one(conn, "SELECT paid_sen FROM orders WHERE id=?", (oid,))["paid_sen"] == 800


def test_whatsapp_links():
    with db() as conn:
        oid, cust = _order(conn)
        conn.execute("UPDATE orders SET paid_sen=300, phone_used='012-798 3745' WHERE id=?", (oid,))
        o = one(conn, "SELECT * FROM orders WHERE id=?", (oid,))
    link = orders_service.customer_wa_link(o, "", "balance")
    assert link.startswith("https://wa.me/60127983745?text=") and "RM2.00" in __import__("urllib.parse").parse.unquote(link)


def _paid_order(conn, eid, pid, sid, cust, qty, phone="1"):
    oid = orders_service.create_order_from_cart(
        conn, eid, cust, {f"{eid}:{pid}:{sid}": qty}, delivery="pickup", address="",
        lat=None, lng=None, zone="west", category="", phone=phone)
    conn.execute("UPDATE orders SET status='paid', paid_sen=total_sen WHERE id=?", (oid,))
    return oid


def test_finalize_puts_order_in_open_batch_and_emails(monkeypatch):
    from app import batches
    mailed, sheets_written = [], []
    monkeypatch.setattr(orders_service, "send_payment_confirmed", lambda *a: mailed.append(a[1]))
    monkeypatch.setattr(batches, "write_sheet", lambda eid: sheets_written.append(eid))
    with db() as conn:
        oid, cust = _order(conn)
        conn.execute("UPDATE orders SET status='paid' WHERE id=?", (oid,))
    orders_service.finalize_payment(oid)
    with db() as conn:
        b = one(conn, "SELECT b.* FROM orders o JOIN batches b ON b.id=o.batch_id WHERE o.id=?", (oid,))
    assert b["number"] == 1 and b["status"] == "open" and len(mailed) == 1 and sheets_written


def test_close_batch_arranges_by_size_and_summed_copies(monkeypatch):
    from app import batches, nextcloud
    from app.config import settings as s
    up = {}
    monkeypatch.setattr(type(s), "nc_instance", lambda self, iid=None: {"id": "src"})
    monkeypatch.setattr(type(s), "nc_print_instance", lambda self: {"id": "dst", "base_url": "https://cloud.johorstudio.cc"})
    monkeypatch.setattr(nextcloud, "download", lambda inst, p: b"img:" + p.encode())
    monkeypatch.setattr(nextcloud, "upload", lambda inst, dest, data, ct: up.__setitem__(dest, data))
    with db() as conn:
        eid, sid, pid, cust = _setup_event(conn)
        # second class with a photo of the SAME file name (a different photo)
        cid2 = conn.execute("INSERT INTO classes(event_id,school,name,folder_path) VALUES (?,?,?,?)",
                            (eid, "SKA", "6 Cerdik", "f/SKA - 6 Cerdik")).lastrowid
        pid2 = conn.execute("INSERT INTO photos(event_id,class_id,filename,rel_path) VALUES (?,?,?,?)",
                            (eid, cid2, "DSC_0001.jpg", "f/SKA - 6 Cerdik/DSC_0001.jpg")).lastrowid
        o1 = _paid_order(conn, eid, pid, sid, cust, 1)
        o2 = _paid_order(conn, eid, pid, sid, cust, 2)      # same photo, same size -> 3 copies
        o3 = _paid_order(conn, eid, pid2, sid, cust, 3)     # other photo, same name, 3 copies
        for o in (o1, o2, o3):
            batches.assign_order(conn, o)
        b = one(conn, "SELECT * FROM batches WHERE event_id=?", (eid,))
        assert batches.start_close(conn, b["id"], "admin")
    monkeypatch.setattr(batches, "write_sheet", lambda eid: None)
    batches.arrange(b["id"])
    base = "Untuk-Cetak/e/Batch-1/4R/3salinan/"
    assert set(up) == {base + "DSC_0001.jpg", base + "DSC_0001 (6 Cerdik).jpg",
                       "Untuk-Cetak/e/Batch-1/senarai-batch-1.csv"}
    assert up[base + "DSC_0001.jpg"].endswith(b"6 Bestari/DSC_0001.jpg")
    with db() as conn:
        b = one(conn, "SELECT * FROM batches WHERE id=?", (b["id"],))
        st = {r["status"] for r in conn.execute("SELECT status FROM orders WHERE batch_id=?", (b["id"],))}
        # a new paid order now starts Batch 2
        o4 = _paid_order(conn, eid, pid, sid, cust, 1)
        b2 = batches.assign_order(conn, o4)
    assert b["status"] == "closed" and b["n_files"] == 2 and b["n_copies"] == 6 and st == {"printing"}
    assert b2["number"] == 2
    assert batches.files_link(b["folder"]) == "https://cloud.johorstudio.cc/apps/files/?dir=/Untuk-Cetak/e/Batch-1"


def test_main_spreadsheet_has_orders_items_and_batches():
    from openpyxl import load_workbook
    from app import batches
    with db() as conn:
        eid, sid, pid, cust = _setup_event(conn)
        o1 = _paid_order(conn, eid, pid, sid, cust, 2)
        batches.assign_order(conn, o1)
        orders_service.create_order_from_cart(conn, eid, cust, {f"{eid}:{pid}:{sid}": 1}, delivery="pickup",
                                              address="", lat=None, lng=None, zone="west", category="", phone="1")
        data = batches.build_sheet(conn, eid)
    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["Semua order", "Item", "Ringkasan batch"]
    rows = list(wb["Semua order"].values)
    assert rows[1][0] == "No. Order" and rows[2][6] == "Batch 1" and rows[3][5] == "awaiting_payment"
    assert list(wb["Ringkasan batch"].values)[1][:2] == ("Batch 1", "open")


def test_backfill_puts_old_paid_orders_in_batch():
    from app import batches
    with db() as conn:
        eid, sid, pid, cust = _setup_event(conn)
        o1 = _paid_order(conn, eid, pid, sid, cust, 1)
        assert batches.backfill(conn) == 1
        assert one(conn, "SELECT batch_id FROM orders WHERE id=?", (o1,))["batch_id"]
