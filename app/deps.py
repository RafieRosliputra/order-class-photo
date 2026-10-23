"""Request-scoped helpers: language, session customer, cart cookie, templating."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer

from . import i18n
from .config import settings
from .database import db, one
from .security import SESSION_COOKIE, read_session
from .utils import gmaps_link, rm, whatsapp_link

CART_COOKIE = "js_cart"
LANG_COOKIE = "js_lang"
_cart_serializer = URLSafeSerializer(settings.secret_key, salt="js-cart")

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# --- language --------------------------------------------------------------
def get_lang(request: Request) -> str:
    q = request.query_params.get("lang")
    if q in i18n.LANGS:
        return q
    c = request.cookies.get(LANG_COOKIE)
    if c in i18n.LANGS:
        return c
    return settings.default_lang


# --- session / customer ----------------------------------------------------
def current_customer(request: Request):
    cid = read_session(request.cookies.get(SESSION_COOKIE))
    if not cid:
        return None
    with db() as conn:
        return one(conn, "SELECT * FROM customers WHERE id=?", (cid,))


# --- cart (signed cookie, survives pre-login) ------------------------------
def read_cart(request: Request) -> dict:
    raw = request.cookies.get(CART_COOKIE)
    if not raw:
        return {}
    try:
        data = _cart_serializer.loads(raw)
        return data if isinstance(data, dict) else {}
    except BadSignature:
        return {}


def write_cart(response, cart: dict) -> None:
    token = _cart_serializer.dumps(cart)
    response.set_cookie(
        CART_COOKIE, token, max_age=30 * 86400, httponly=True,
        samesite="lax", secure=not settings.is_dev,
    )


def cart_count(cart: dict) -> int:
    return sum(int(v) for v in cart.values())


def cart_event_id(cart: dict) -> int | None:
    """Cart is scoped to one event; return it (keys are 'eventid:photoid:sizeid')."""
    for key in cart:
        parts = key.split(":")
        if len(parts) == 3:
            return int(parts[0])
    return None


# --- templating ------------------------------------------------------------
def render(request: Request, name: str, ctx: dict | None = None):
    lang = get_lang(request)
    customer = current_customer(request)
    cart = read_cart(request)
    base = {
        "request": request,
        "lang": lang,
        "other_lang": "en" if lang == "ms" else "ms",
        "t": lambda key: i18n.t(lang, key),
        "slabel": lambda s: i18n.status_label(lang, s),
        "rm": rm,
        "settings": settings,
        "customer": customer,
        "cart_count": cart_count(cart),
        "whatsapp_link": whatsapp_link,
        "gmaps_link": gmaps_link,
        "umami_src": settings.umami_src,
        "umami_id": settings.umami_website_id,
        "status_flow": i18n.STATUS_KEYS,
    }
    if ctx:
        base.update(ctx)
    return templates.TemplateResponse(name, base)


def json_dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
