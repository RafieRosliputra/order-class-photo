"""Copy paid-order originals to the Nextcloud print folder.

Layout (matches the studio's batch-print workflow):

    <PRINT_FOLDER>/<event-slug>/<SIZE>/<N>salinan/<original filename>

Originals are streamed from Nextcloud at full quality and re-uploaded under the
print folder; local disk never stores the originals.
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
    """Copy every item's original into the print folder. Returns the paths written."""
    order = one(conn, "SELECT * FROM orders WHERE id=?", (order_id,))
    event = one(conn, "SELECT slug FROM events WHERE id=?", (order["event_id"],))
    base = f"{settings.nextcloud_print_folder.strip('/')}/{event['slug']}"
    items = query(conn, "SELECT * FROM order_items WHERE order_id=?", (order_id,))

    written: list[str] = []
    if not nextcloud.is_configured():
        return written

    for it in items:
        data = nextcloud.download(it["rel_path"])
        fname = it["filename"]
        dest = f"{base}/{it['size_code']}/{it['qty']}salinan/{fname}"
        ext = posixpath.splitext(fname)[1].lower()
        nextcloud.upload(dest, data, CONTENT_TYPES.get(ext, "application/octet-stream"))
        written.append(dest)
    return written
