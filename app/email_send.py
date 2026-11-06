"""Transactional email via SMTP relay: login code and payment-confirmed
(bilingual, to customers), plus a short admin notice when a receipt is
auto-confirmed or needs a manual check.

If SMTP is not configured, emails are logged to stdout instead (and in dev the
login code is printed so you can log in without a mail server).
"""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import settings
from .utils import rm

BRAND = "JohorStudio.com"

_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates" / "emails")),
    autoescape=select_autoescape(["html"]),
)


def _send(to: str, subject: str, html: str, text: str) -> None:
    if not settings.smtp_host:
        print(f"[email:disabled] to={to} subject={subject!r}\n{text}\n")
        return
    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    ctx = ssl.create_default_context()
    if not settings.smtp_verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    pw = _smtp_password()
    if settings.smtp_starttls:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
            s.starttls(context=ctx)
            if settings.smtp_user:
                s.login(settings.smtp_user, pw)
            s.send_message(msg)
    else:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30, context=ctx) as s:
            if settings.smtp_user:
                s.login(settings.smtp_user, pw)
            s.send_message(msg)


def _smtp_password() -> str:
    """Password from SMTP_PASSWORD_FILE if set (live sync with mail-admin), else env."""
    if settings.smtp_password_file:
        try:
            val = Path(settings.smtp_password_file).read_text(encoding="utf-8").strip()
            if val:
                return val
        except OSError:
            pass
    return settings.smtp_password


def send_login_code(to: str, code: str) -> None:
    subject = f"Kod log masuk / Login code: {code}"
    html = _env.get_template("login_code.html").render(code=code, brand=BRAND)
    text = (
        f"Kod log masuk anda: {code}\n"
        f"Your login code: {code}\n\n"
        f"Sah untuk {settings.login_code_ttl_seconds // 60} minit / "
        f"Valid for {settings.login_code_ttl_seconds // 60} minutes.\n— {BRAND}"
    )
    _send(to, subject, html, text)


def send_payment_confirmed(to: str, order_no: str, total_sen: int, status_url: str) -> None:
    subject = f"Bayaran diterima / Payment received — {order_no}"
    html = _env.get_template("payment_confirmed.html").render(
        order_no=order_no, total=rm(total_sen), status_url=status_url, brand=BRAND,
    )
    text = (
        f"Terima kasih! Bayaran untuk order {order_no} telah disahkan ({rm(total_sen)}).\n"
        f"Thank you! Payment for order {order_no} is confirmed ({rm(total_sen)}).\n\n"
        f"Semak status / Check status: {status_url}\n— {BRAND}"
    )
    _send(to, subject, html, text)


def send_admin_notice(to: str, kind: str, order, receipt, admin_url: str) -> None:
    """Admin email: an order was auto-confirmed as paid, or a receipt needs a check."""
    amt = rm(receipt["amount_sen"]) if receipt and receipt["amount_sen"] else "tidak dapat dibaca"
    if kind == "paid":
        subject = f"Order dah bayar — {order['order_no']} ({rm(order['total_sen'])})"
        head = "Ada order dah bayar. OCR sahkan jumlah resit sama dengan jumlah order."
    else:
        subject = f"Resit perlu semakan — {order['order_no']} ({rm(order['total_sen'])})"
        head = "Customer dah upload resit, tapi OCR tak dapat sahkan. Sila semak di admin."
    rows = [
        ("Order", order["order_no"]),
        ("Majlis", order["event_name"]),
        ("Customer", f"{order['cust_name'] or ''} {order['cust_email']} {order['phone_used'] or ''}".strip()),
        ("Jumlah order", rm(order["total_sen"])),
        ("Dibayar (diterima)", rm(order["paid_sen"])),
        ("Amaun resit (OCR)", amt),
        ("No. rujukan", (receipt["receipt_no"] if receipt else "") or "—"),
        ("Keputusan OCR", (receipt["ocr_note"] if receipt else "") or "—"),
        ("Status", order["status"]),
    ]
    text = f"Admin rafierosliputra,\n\n{head}\n\n" + "\n".join(f"{k}: {v}" for k, v in rows) + \
        f"\n\nBuka order: {admin_url}\n— {BRAND}"
    from html import escape
    html = (
        f"<p>Admin rafierosliputra,</p><p><strong>{escape(head)}</strong></p>"
        "<table cellpadding='4' style='border-collapse:collapse;font:14px sans-serif'>"
        + "".join(f"<tr><td style='color:#666'>{escape(k)}</td><td><strong>{escape(str(v))}</strong></td></tr>"
                  for k, v in rows)
        + f"</table><p><a href='{escape(admin_url)}'>Buka order di admin</a></p><p>— {BRAND}</p>"
    )
    _send(to, subject, html, text)
