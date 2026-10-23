"""Minimal Nextcloud WebDAV client (list / download / upload / mkdir).

Supports MULTIPLE Nextcloud instances: every function takes an `inst` dict
({id,label,base_url,user,password,webdav_root}) from settings.nc_instances().
Originals are read from the event's instance; print output is written to the
configured print instance. Photo originals are never cached locally — only
WebP previews are.
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass
from urllib.parse import unquote, quote
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


def _client(inst: dict) -> httpx.Client:
    return httpx.Client(
        base_url=inst["base_url"],
        auth=(inst.get("user", ""), inst.get("password", "")),
        timeout=60,
        follow_redirects=True,
    )


def _root(inst: dict) -> str:
    return (inst.get("webdav_root") or "/remote.php/dav/files/").strip("/")


def _full(inst: dict, path: str) -> str:
    rel = path.strip("/")
    joined = f"{_root(inst)}/{rel}" if rel else _root(inst)
    return "/" + "/".join(quote(s) for s in joined.split("/"))


def _rel_from_href(inst: dict, href: str) -> str:
    href = unquote(href)
    root = "/" + _root(inst) + "/"
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


def list_dir(inst: dict, path: str = "") -> list[DavEntry]:
    with _client(inst) as c:
        r = c.request("PROPFIND", _full(inst, path), headers={"Depth": "1"}, content=PROPFIND_BODY)
        r.raise_for_status()
    entries: list[DavEntry] = []
    tree = ET.fromstring(r.content)
    self_rel = path.strip("/")
    for resp in tree.findall(f"{_DAV}response"):
        href = resp.findtext(f"{_DAV}href") or ""
        rel = _rel_from_href(inst, href)
        if rel == self_rel:
            continue
        prop = resp.find(f"{_DAV}propstat/{_DAV}prop")
        if prop is None:
            continue
        is_dir = prop.find(f"{_DAV}resourcetype/{_DAV}collection") is not None
        size = int(prop.findtext(f"{_DAV}getcontentlength") or 0)
        etag = (prop.findtext(f"{_DAV}getetag") or "").strip('"')
        name = posixpath.basename(rel.rstrip("/"))
        entries.append(DavEntry(name=name, path=rel, is_dir=is_dir, size=size, etag=etag))
    entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
    return entries


def walk_images(inst: dict, folder: str) -> list[DavEntry]:
    return [e for e in list_dir(inst, folder)
            if not e.is_dir and posixpath.splitext(e.name)[1].lower() in IMAGE_EXT]


def subfolders(inst: dict, folder: str = "") -> list[DavEntry]:
    return [e for e in list_dir(inst, folder) if e.is_dir]


def download(inst: dict, path: str) -> bytes:
    with _client(inst) as c:
        r = c.get(_full(inst, path))
        r.raise_for_status()
        return r.content


def _mkdir(inst: dict, path: str) -> None:
    with _client(inst) as c:
        r = c.request("MKCOL", _full(inst, path))
        if r.status_code not in (201, 405):
            r.raise_for_status()


def ensure_dirs(inst: dict, path: str) -> None:
    cur = ""
    for p in path.strip("/").split("/"):
        cur = f"{cur}/{p}".strip("/")
        _mkdir(inst, cur)


def upload(inst: dict, path: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    parent = posixpath.dirname(path)
    if parent:
        ensure_dirs(inst, parent)
    with _client(inst) as c:
        r = c.put(_full(inst, path), content=data, headers={"Content-Type": content_type})
        r.raise_for_status()


def is_configured() -> bool:
    return bool(settings.nc_instances())
