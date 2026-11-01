from app.security import generate_code, normalise_code


def test_code_is_four_digits_no_space():
    for _ in range(200):
        c = generate_code()
        assert len(c) == 4 and c.isdigit()


def test_normalise_accepts_spaced_and_plain():
    assert normalise_code("2188") == "2188"
    assert normalise_code("21 88") == "2188"
    assert normalise_code(" 21-88 ") == "2188"
    assert normalise_code("") == ""
