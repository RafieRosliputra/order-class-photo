"""Scheduled background jobs (APScheduler): daily DB backup + trash sweep."""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import backup
from .utils import TZ

log = logging.getLogger("tasks")
_scheduler: BackgroundScheduler | None = None


def _daily_maintenance() -> None:
    try:
        n = backup.sweep_trash()
        b = backup.backup_db()
        log.info("maintenance: swept %s trash files, backup=%s", n, b)
    except Exception:  # noqa: BLE001
        log.exception("daily maintenance failed")


def start_scheduler() -> None:
    global _scheduler
    if _scheduler:
        return
    _scheduler = BackgroundScheduler(timezone=TZ)
    _scheduler.add_job(_daily_maintenance, CronTrigger(hour=3, minute=30),
                       id="daily_maintenance", replace_existing=True)
    _scheduler.start()
    log.info("scheduler started")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
