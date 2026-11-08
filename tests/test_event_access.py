"""Event gallery password + secret direct link."""
from types import SimpleNamespace

from app import event_access
from app.database import db, one
from tests.test_orders import _setup_event


class Req:
    def __init__(self, cookies=None, headers=None):
        self.cookies, self.headers, self.client = cookies or {}, headers or {}, SimpleNamespace(host="1.2.3.4")


class Resp:
    def __init__(self):
        self.cookies = {}

    def set_cookie(self, name, value, **kw):
        self.cookies[name] = (value, kw)


def _event(conn, password="", key="abc123key"):
    eid, *_ = _setup_event(conn)
    conn.execute("UPDATE events SET access_password=?, access_key=? WHERE id=?", (password, key, eid))
    return one(conn, "SELECT * FROM events WHERE id=?", (eid,))


def test_open_event_needs_nothing():
    with db() as conn:
        ev = _event(conn)
    assert not event_access.is_locked(ev) and event_access.has_access(Req(), ev)


def test_password_cookie_grants_access_30_days():
    with db() as conn:
        ev = _event(conn, "konvo2026")
    assert event_access.is_locked(ev) and not event_access.has_access(Req(), ev)
    assert not event_access.password_ok(ev, "salah") and event_access.password_ok(ev, " konvo2026 ")
    r = Resp()
    event_access.grant(r, ev)
    name = f"js_ev_{ev['id']}"
    value, kw = r.cookies[name]
    assert kw["max_age"] == 30 * 86400 and kw["httponly"]
    assert event_access.has_access(Req({name: value}), ev)
    assert not event_access.has_access(Req({name: "forged"}), ev)


def test_new_password_or_new_link_revokes_old_cookie():
    with db() as conn:
        ev = _event(conn, "pw1")
        r = Resp()
        event_access.grant(r, ev)
        cookie = {f"js_ev_{ev['id']}": r.cookies[f"js_ev_{ev['id']}"][0]}
        conn.execute("UPDATE events SET access_key='newkey' WHERE id=?", (ev["id"],))
        rotated = one(conn, "SELECT * FROM events WHERE id=?", (ev["id"],))
        conn.execute("UPDATE events SET access_password='pw2' WHERE id=?", (ev["id"],))
        changed = one(conn, "SELECT * FROM events WHERE id=?", (ev["id"],))
    assert event_access.has_access(Req(cookie), ev)
    assert not event_access.has_access(Req(cookie), rotated)
    assert not event_access.has_access(Req(cookie), changed)
    assert not event_access.key_ok(rotated, "abc123key") and event_access.key_ok(rotated, "newkey")


def test_direct_url_and_throttle():
    with db() as conn:
        ev = _event(conn, "pw", key="K1")
    assert event_access.direct_url("https://shop.johorstudio.com", ev) == "https://shop.johorstudio.com/e/e?k=K1"
    ip = "9.9.9.9"
    for _ in range(event_access.MAX_FAILS):
        assert not event_access.too_many_fails(ip, ev["id"])
        event_access.record_fail(ip, ev["id"])
    assert event_access.too_many_fails(ip, ev["id"])
    assert not event_access.too_many_fails("8.8.8.8", ev["id"])
