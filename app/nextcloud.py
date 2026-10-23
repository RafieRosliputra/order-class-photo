"""Minimal Nextcloud WebDAV client (list / download / upload / mkdir).

Originals are read-only; print output is written under NEXTCLOUD_PRINT_FOLDER.
Photo originals are never cached to local disk — only WebP previews are.
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, quote
from xml.etree import ElementTree as ET

import httpx

from .config import settings

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic"}
_DAV = "{DAV:}"


@dataclass
class DavEntry:
    name: str
    path: str          # path relative to the WebDAV root (no leading slash)
    is_dir: bool
    size: int
    etag: str


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.nextcloud_base_url,
        auth=(settings.nextcloud_user, settings.nextcloud_app_password),
        timeout=60,
        follow_redirects=True,
    )


def _full(path: str) -> str:
    """Join WebDAV root + path, URL-encoding each segment."""
    root = settings.nextcloud_webdav_root.strip("/")
    rel = path.strip("/")
    segments = [quote(s) for s in (f"{root}/{rel}" if rel else root).split("/")]
    return "/" + "/".join(segments)


def _rel_from_href(href: str) -> str:
    """Strip the WebDAV root prefix from an href to get a root-relative path."""
    href = unquote(href)
    root = "/" + settings.nextcloud_webdav_root.strip("/") + "/"
    idx = href.find(root)
    if idx != -1:
        return href[idx + len(root):].strip("/")
    return href.strip("/")


PROPFIND_BODY = (
    '<?xml version="1.0"?>'
    '<d:propfind xmlns:d="DAV:"><d:prop>'
    "<d:resourcetype/><d:getcontentlength/><d:getetag/>"
    "</d:prop></d:propfind>"
)


def list_dir(path: str = "") -> list[DavEntry]:
    """List immediate children of a folder (depth 1)."""
    url = _full(path)
    with _client() as c:
        r = c.request("PROPFIND", url, headers={"Depth": "1"}, content=PROPFIND_BODY)
        r.raise_for_status()
    entries: list[DavEntry] = []
    tree = ET.fromstring(r.content)
    self_rel = path.strip("/")
    for resp in tree.findall(f"{_DAV}response"):
        href = resp.findtext(f"{_DAV}href") or ""
        rel = _rel_from_href(href)
        if rel == self_rel:
            continue  # skip the folder itself
        propstat = resp.find(f"{_DAV}propstat/{_DAV}prop")
        if propstat is None:
            continue
        is_dir = propstat.find(f"{_DAV}resourcetype/{_DAV}collection") is not None
        size = int(propstat.findtext(f"{_DAV}getcontentlength") or 0)
        etag = (propstat.findtext(f"{_DAV}getetag") or "").strip('"')
        name = posixpath.basename(rel.rstrip("/"))
        entries.append(DavEntry(name=name, path=rel, is_dir=is_dir, size=size, etag=etag))
    entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
    return entries


def walk_images(folder: str) -> list[DavEntry]:
    """Immediate image files inside a folder."""
    return [
        e for e in list_dir(folder)
        if not e.is_dir and posixpath.splitext(e.name)[1].lower() in IMAGE_EXT
    ]


def subfolders(folder: str) -> list[DavEntry]:
    return [e for e in list_dir(folder) if e.is_dir]


def download(path: str) -> bytes:
    with _client() as c:
        r = c.get(_full(path))
        r.raise_for_status()
        return r.content


def _mkdir(path: str) -> None:
    with _client() as c:
        r = c.request("MKCOL", _full(path))
        if r.status_code not in (201, 405):  # 405 = already exists
            r.raise_for_status()


def ensure_dirs(path: str) -> None:
    """Create a folder and all missing parents, relative to the WebDAV root."""
    parts = path.strip("/").split("/")
    cur = ""
    for p in parts:
        cur = f"{cur}/{p}".strip("/")
        _mkdir(cur)


def upload(path: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    ensure_dirs(posixpath.dirname(path))
    with _client() as c:
        r = c.put(_full(path), content=data, headers={"Content-Type": content_type})
        r.raise_for_status()


def is_configured() -> bool:
    return bool(settings.nextcloud_base_url and settings.nextcloud_app_password)
