"""
Точка входа планировщика.

Запускается отдельно от Flask:
    python -m scheduler.runner
"""

import asyncio
import contextlib
import logging
import sys
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# Гарантируем, что корень проекта в sys.path при запуске как скрипт
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from scheduler.jobs import (  # noqa: E402
    job_healthcheck,
    job_process_events,
    job_scrape_cbr,
    job_sync_grist,
    job_sync_sheets,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scheduler")


async def _run() -> None:
    app = create_app()
    scheduler = AsyncIOScheduler(timezone="UTC")

    scheduler.add_job(
        job_process_events,
        IntervalTrigger(seconds=30),
        args=[app],
        id="process_events",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        job_sync_grist,
        IntervalTrigger(minutes=30),
        args=[app],
        id="sync_grist",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        job_healthcheck,
        CronTrigger(hour="*/6", minute=0),
        args=[app],
        id="healthcheck",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        job_scrape_cbr,
        IntervalTrigger(hours=6),
        args=[app],
        id="scrape_cbr",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        job_sync_sheets,
        IntervalTrigger(hours=1),
        args=[app],
        id="sync_sheets",
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    logger.info("Scheduler started. Jobs:")
    logger.info("  process_events — every 30 sec")
    logger.info("  sync_grist     — every 30 min")
    logger.info("  healthcheck    — every 6 hours (on the hour)")
    logger.info("  scrape_cbr     — every 6 hours")
    logger.info("  sync_sheets    — every 1 hour")

    try:
        await asyncio.Event().wait()  # ждём вечно
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown signal received")
    finally:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")


def main() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run())


if __name__ == "__main__":
    main()
