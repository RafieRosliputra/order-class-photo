"""Daily SQLite backup + retention pruning, and receipt-trash sweeping."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .config import settings
from .utils import local_now


def backup_db() -> Path | None:
    src = Path(settings.sqlite_path)
    if not src.exists():
        return None
    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.backups_dir / f"app-{local_now():%Y%m%d-%H%M}.sqlite3"
    # consistent online backup
    with sqlite3.connect(settings.sqlite_path) as s, sqlite3.connect(dest) as d:
        s.backup(d)
    _prune(settings.backups_dir, settings.backup_keep_days, "*.sqlite3")
    return dest


def sweep_trash() -> int:
    """Delete receipt originals older than TRASH_RETENTION_DAYS. Returns count."""
    return _prune(settings.trash_dir, settings.trash_retention_days, "*")


def clear_trash_all() -> int:
    """Delete ALL receipt originals now (admin 'Clear trash' button). Returns count."""
    folder = settings.trash_dir
    if not folder.exists():
        return 0
    removed = 0
    for p in folder.glob("*"):
        if p.is_file():
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def _prune(folder: Path, keep_days: int, pattern: str) -> int:
    if not folder.exists():
        return 0
    cutoff = time.time() - keep_days * 86400
    removed = 0
    for p in folder.glob(pattern):
        if p.is_file() and p.stat().st_mtime < cutoff:
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed
