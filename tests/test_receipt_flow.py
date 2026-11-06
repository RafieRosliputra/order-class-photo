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
