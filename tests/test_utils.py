from app.utils import rm, slugify, split_school_class, to_sen


def test_money():
    assert to_sen("12.50") == 1250
    assert rm(1250) == "RM12.50"
    assert rm(0) == "RM0.00"


def test_slugify():
    assert slugify("Konvo Tadika X 2026!") == "konvo-tadika-x-2026"


def test_split_school_class():
    assert split_school_class("SKA - 3 Bestari", " - ") == ("SKA", "3 Bestari")
    assert split_school_class("6 Cerdik", " - ") == ("", "6 Cerdik")
