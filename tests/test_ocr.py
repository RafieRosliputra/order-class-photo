from app.ocr import parse_text

MAYBANK = """
Maybank2u
Transfer Successful
Amount  RM 50.00
Reference No: MB123456789
Date: 15/11/2026  10:42:03
To: PROMEDIA CREATIVE SOLUTIONS
"""

CIMB = """
CIMB Clicks
Payment Receipt
Total MYR 1,235.00
Ref ID CIMB0098231
20-11-2026 09:15 PM
"""


def test_amount_and_ref_maybank():
    r = parse_text(MAYBANK)
    assert r["amount_sen"] == 5000
    assert r["receipt_no"] == "MB123456789"
    assert r["bank"] == "Maybank"
    assert r["receipt_date"] == "2026-11-15"
    assert r["receipt_time"].startswith("10:42")


def test_amount_with_thousands_and_pm():
    r = parse_text(CIMB)
    assert r["amount_sen"] == 123500
    assert r["bank"] == "CIMB"
    assert r["receipt_time"] == "21:15"


def test_largest_amount_when_unlabelled():
    txt = "RM5.00 service\nGrand RM 42.50"
    r = parse_text(txt)
    assert r["amount_sen"] == 4250


def test_no_amount():
    assert parse_text("hello world")["amount_sen"] is None
