"""Disk hygiene for an unattended, always-on web service: periodically delete
job directories nobody has touched in a while.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path

from dvr_noise_cutter.web.jobs import JobStore

logger = logging.getLogger(__name__)


def find_expired_job_dirs(job_dirs: list[tuple[Path, float]], now: float, ttl_hours: float) -> list[Path]:
    """job_dirs: (path, mtime_epoch_seconds) pairs. Returns paths whose age exceeds ttl_hours."""
    ttl_seconds = ttl_hours * 3600
    return [path for path, mtime in job_dirs if now - mtime > ttl_seconds]


async def sweep_loop(jobs_dir: Path, ttl_hours: float, store: JobStore, interval_sec: int = 3600) -> None:
    while True:
        try:
            job_dirs = [(p, p.stat().st_mtime) for p in jobs_dir.iterdir() if p.is_dir()]
            for path in find_expired_job_dirs(job_dirs, time.time(), ttl_hours):
                shutil.rmtree(path, ignore_errors=True)
                store.remove(path.name)
        except Exception:
            logger.exception("TTL sweep failed")
        await asyncio.sleep(interval_sec)
