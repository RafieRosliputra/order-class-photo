"""Public pages: home, event gallery, media, language, terms, health."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from .. import i18n, imaging, nextcloud
from ..config import settings
from ..database import db, one, query
from ..deps import LANG_COOKIE, render
from ..utils import local_now

router = APIRouter()


def _event_open(event) -> bool:
    if event["status"] != "open":
        return False
    if event["close_date"]:
        try:
            return local_now().date().isoformat() <= event["close_date"]
        except Exception:  # noqa: BLE001
            return True
    return True


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/lang/{lang}")
def set_lang(lang: str, request: Request):
    nxt = request.query_params.get("next", "/")
    resp = RedirectResponse(nxt, status_code=303)
    if lang in i18n.LANGS:
        resp.set_cookie(LANG_COOKIE, lang, max_age=365 * 86400, samesite="lax")
    return resp


@router.get("/")
def home(request: Request):
    with db() as conn:
        events = query(conn, "SELECT * FROM events ORDER BY created_at DESC")
        events = [e for e in events if _event_open(e)]
    return render(request, "home.html", {"events": events})


@router.get("/terms")
def terms(request: Request):
    return render(request, "terms.html", {})


@router.get("/e/{slug}")
def event_gallery(slug: str, request: Request):
    with db() as conn:
        event = one(conn, "SELECT * FROM events WHERE slug=?", (slug,))
        if not event:
            return render(request, "not_found.html", {})
        classes = query(conn, "SELECT * FROM classes WHERE event_id=? ORDER BY school, sort, name",
                        (event["id"],))
        photos = query(
            conn,
            """SELECT p.*, c.school AS school, c.name AS class_name
               FROM photos p JOIN classes c ON c.id=p.class_id
               WHERE p.event_id=? ORDER BY c.school, c.name, p.sort, p.filename""",
            (event["id"],),
        )
        sizes = query(conn, "SELECT * FROM sizes WHERE event_id=? ORDER BY sort, price_sen",
                      (event["id"],))
    schools = sorted({c["school"] for c in classes if c["school"]})
    return render(request, "gallery.html", {
        "event": event, "classes": classes, "photos": photos, "sizes": sizes,
        "schools": schools, "is_open": _event_open(event),
    })


def _serve_cached(rel_path: str, photo, kind: str) -> Response:
    """Serve a cached WebP; lazily generate from Nextcloud if missing."""
    full = settings.data_path / rel_path if rel_path else None
    if not full or not full.exists():
        # lazy generation fallback
        try:
            with db() as conn:
                ev = one(conn, "SELECT nextcloud_id FROM events WHERE id=?", (photo["event_id"],))
            inst = settings.nc_instance(ev["nextcloud_id"] if ev else None)
            data = nextcloud.download(inst, photo["rel_path"])
            made = imaging.make_previews(data)
            with db() as conn:
                conn.execute(
                    "UPDATE photos SET thumb_path=?, preview_path=?, width=?, height=? WHERE id=?",
                    (made["thumb_path"], made["preview_path"], made["width"], made["height"], photo["id"]),
                )
            rel = made["thumb_path"] if kind == "thumb" else made["preview_path"]
            full = settings.data_path / rel
        except Exception:  # noqa: BLE001
            placeholder = Path(__file__).parent.parent / "static" / "img" / "placeholder.webp"
            if placeholder.exists():
                return FileResponse(placeholder, media_type="image/webp")
            return Response(status_code=404)
    resp = FileResponse(full, media_type="image/webp")
    # discourage trivial caching/hotlinking of the asset path
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


@router.get("/p/{photo_id}/thumb.webp")
def photo_thumb(photo_id: int):
    with db() as conn:
        photo = one(conn, "SELECT * FROM photos WHERE id=?", (photo_id,))
    if not photo:
        return Response(status_code=404)
    return _serve_cached(photo["thumb_path"], photo, "thumb")


@router.get("/p/{photo_id}/large.webp")
def photo_large(photo_id: int):
    with db() as conn:
        photo = one(conn, "SELECT * FROM photos WHERE id=?", (photo_id,))
    if not photo:
        return Response(status_code=404)
    return _serve_cached(photo["preview_path"], photo, "preview")
