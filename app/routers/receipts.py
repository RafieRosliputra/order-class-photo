"""Receipt upload + OCR verification."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

from ..config import settings
from ..database import db, one
from ..deps import current_customer, render
from ..orders_service import finalize_payment, process_receipt

router = APIRouter()

ALLOWED = {"image/png", "image/jpeg", "image/jpg", "application/pdf"}


@router.post("/order/{order_no}/receipt")
async def upload_receipt(order_no: str, request: Request, background: BackgroundTasks,
                         files: list[UploadFile] = File(...), forced: str = Form("")):
    customer = current_customer(request)
    if not customer:
        return RedirectResponse(f"/login?next=/order/{order_no}", status_code=303)

    with db() as conn:
        order = one(conn, "SELECT * FROM orders WHERE order_no=?", (order_no,))
        if not order or order["customer_id"] != customer["id"]:
            return render(request, "not_found.html", {})

    force = forced == "1"
    duplicate_hit = None
    paid_now = False
    max_bytes = settings.receipt_max_mb * 1024 * 1024

    for up in files:
        if up.content_type not in ALLOWED:
            continue
        data = await up.read()
        if not data or len(data) > max_bytes:
            continue
        with db() as conn:
            res = process_receipt(conn, order["id"], customer["id"], data,
                                  up.filename or "resit", up.content_type, forced=force)
        if res.get("duplicate") and not res.get("ok"):
            duplicate_hit = res.get("receipt_no", "")
            break  # stop; ask customer to confirm
        if res.get("just_paid"):
            paid_now = True

    if duplicate_hit is not None:
        return render(request, "receipt_duplicate.html",
                      {"order_no": order_no, "receipt_no": duplicate_hit})

    if paid_now:
        background.add_task(finalize_payment, order["id"])

    return RedirectResponse(f"/order/{order_no}?uploaded=1", status_code=303)
