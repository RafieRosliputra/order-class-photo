"""FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .deps import render
from .routers import admin, auth, cart, checkout, orders, public, receipts
from .tasks import shutdown_scheduler, start_scheduler

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    init_db()
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="Johor Studio — Photo Order", lifespan=lifespan, docs_url=None, redoc_url=None)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(public.router)
app.include_router(cart.router)
app.include_router(auth.router)
app.include_router(checkout.router)
app.include_router(orders.router)
app.include_router(receipts.router)
app.include_router(admin.router)


@app.exception_handler(404)
async def not_found(request: Request, exc):
    if request.url.path.startswith(("/static", "/p/", "/healthz")):
        return RedirectResponse("/", status_code=303) if request.url.path == "" else \
            render(request, "not_found.html", {})
    return render(request, "not_found.html", {})
