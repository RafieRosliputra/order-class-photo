"""Passwordless login: emailed 2×2-digit code, then phone capture."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import ValidationError
from email_validator import validate_email, EmailNotValidError

from ..config import settings
from ..database import db, one
from ..deps import render
from ..email_send import send_login_code
from ..security import SESSION_COOKIE, issue_session, start_login, verify_code

router = APIRouter()
_login_cookie = "js_login"
_login_ser = URLSafeSerializer(settings.secret_key, salt="js-login")


def _set_pending(resp, email: str, nxt: str):
    resp.set_cookie(_login_cookie, _login_ser.dumps({"email": email, "next": nxt}),
                    max_age=1800, httponly=True, samesite="lax", secure=not settings.is_dev)


def _get_pending(request: Request) -> dict:
    raw = request.cookies.get(_login_cookie)
    if not raw:
        return {}
    try:
        return _login_ser.loads(raw)
    except BadSignature:
        return {}


@router.get("/login")
def login_page(request: Request):
    nxt = request.query_params.get("next", "/")
    if request.cookies.get(SESSION_COOKIE):
        return RedirectResponse(nxt, status_code=303)
    return render(request, "login_email.html", {"next": nxt})


@router.post("/login/request")
def login_request(request: Request, background: BackgroundTasks,
                  email: str = Form(...), next: str = Form("/")):
    email = email.strip().lower()
    try:
        email = validate_email(email, check_deliverability=False).normalized
    except EmailNotValidError:
        return render(request, "login_email.html", {"next": next, "error": "invalid_email"})

    with db() as conn:
        ok, payload, wait = start_login(conn, email)
    if not ok:
        resp = render(request, "login_email.html",
                      {"next": next, "error": payload, "wait": wait})
        return resp
    background.add_task(send_login_code, email, payload)
    resp = render(request, "login_code.html",
                  {"next": next, "email": email,
                   "dev_code": payload if (settings.is_dev or not settings.smtp_host) else None})
    _set_pending(resp, email, next)
    return resp


@router.post("/login/verify")
def login_verify(request: Request, code: str = Form(...), next: str = Form("/")):
    pending = _get_pending(request)
    email = pending.get("email")
    if not email:
        return RedirectResponse("/login", status_code=303)
    with db() as conn:
        ok, msg = verify_code(conn, email, code)
        if not ok:
            return render(request, "login_code.html",
                          {"next": next, "email": email, "error": msg})
        cust = one(conn, "SELECT * FROM customers WHERE email=?", (email,))
        if not cust:
            cid = conn.execute("INSERT INTO customers(email) VALUES (?)", (email,)).lastrowid
        else:
            cid = cust["id"]
        conn.execute("UPDATE customers SET last_login=datetime('now') WHERE id=?", (cid,))
        has_phone = bool(cust and cust["phone"])

    dest = next if has_phone else f"/login/phone?next={next}"
    resp = RedirectResponse(dest, status_code=303)
    resp.set_cookie(SESSION_COOKIE, issue_session(cid), max_age=settings.session_days * 86400,
                    httponly=True, samesite="lax", secure=not settings.is_dev)
    resp.delete_cookie(_login_cookie)
    return resp


@router.get("/login/phone")
def phone_page(request: Request):
    from ..deps import current_customer
    if not current_customer(request):
        return RedirectResponse("/login", status_code=303)
    return render(request, "login_phone.html", {"next": request.query_params.get("next", "/")})


@router.post("/login/phone")
def phone_save(request: Request, phone: str = Form(...), name: str = Form(""), next: str = Form("/")):
    from ..deps import current_customer
    cust = current_customer(request)
    if not cust:
        return RedirectResponse("/login", status_code=303)
    phone = phone.strip()
    with db() as conn:
        history = json.loads(cust["phone_history"] or "[]")
        history.append({"phone": phone, "at": datetime.now(timezone.utc).isoformat()})
        conn.execute("UPDATE customers SET phone=?, phone_history=?, name=COALESCE(NULLIF(?,''), name) WHERE id=?",
                     (phone, json.dumps(history), name.strip(), cust["id"]))
    return RedirectResponse(next, status_code=303)


@router.get("/logout")
def logout(request: Request):
    nxt = request.query_params.get("next", "/")
    resp = RedirectResponse(nxt, status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp
