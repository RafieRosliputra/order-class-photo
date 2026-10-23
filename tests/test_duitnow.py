from app.duitnow import build_dynamic, crc16, parse_tlv

# A minimal but well-formed static DuitNow-style payload (ASCII).
STATIC = (
    "000201"          # payload format indicator
    "010211"          # point of initiation = 11 (static)
    "5303458"         # currency = MYR
    "5802MY"
    "5909Test Shop"
    "6005Johor"
    "6304ABCD"        # dummy CRC (recomputed on build)
)


def test_crc16_known_vector():
    # CRC-16/CCITT-FALSE("123456789") == 0x29B1
    assert crc16("123456789") == "29B1"


def test_build_dynamic_injects_amount_and_reference():
    out = build_dynamic(STATIC, amount_sen=4000, reference="0127983745", ref_subtag="05")
    # point of initiation becomes dynamic (12)
    assert "010212" in out
    # amount 40.00 present as tag 54
    assert "540540.00" in out
    # phone reference present inside additional-data template
    assert "0127983745" in out
    # CRC at the end is valid for the preceding body
    assert crc16(out[:-4]) == out[-4:]


def test_build_dynamic_is_parseable():
    out = build_dynamic(STATIC, amount_sen=1550, reference="60123456789")
    tags = dict(parse_tlv(out))
    assert tags["01"] == "12"
    assert tags["54"] == "15.50"
    assert "62" in tags and "63" in tags
