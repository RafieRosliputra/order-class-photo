"""Copy paid-order originals to the Nextcloud print folder.

Originals are streamed from the EVENT's Nextcloud instance; the print copies are
written to the configured PRINT instance (settings.nc_print_instance), under:

    <PRINT_FOLDER>/<event-slug>/<SIZE>/<N>salinan/<original filename>
"""
from __future__ import annotations

import posixpath

from . import nextcloud
from .config import settings
from .database import one, query

CONTENT_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".tif": "image/tiff", ".tiff": "image/tiff",
}


def copy_order_to_print(conn, order_id: int) -> list[str]:
    order = one(conn, "SELECT * FROM orders WHERE id=?", (order_id,))
    event = one(conn, "SELECT slug, nextcloud_id FROM events WHERE id=?", (order["event_id"],))
    src = settings.nc_instance(event["nextcloud_id"])
    dst = settings.nc_print_instance()
    written: list[str] = []
    if not (src and dst):
        return written

    base = f"{settings.nextcloud_print_folder.strip('/')}/{event['slug']}"
    for it in query(conn, "SELECT * FROM order_items WHERE order_id=?", (order_id,)):
        data = nextcloud.download(src, it["rel_path"])
        fname = it["filename"]
        dest = f"{base}/{it['size_code']}/{it['qty']}salinan/{fname}"
        ext = posixpath.splitext(fname)[1].lower()
        nextcloud.upload(dst, dest, data, CONTENT_TYPES.get(ext, "application/octet-stream"))
        written.append(dest)
    return written
