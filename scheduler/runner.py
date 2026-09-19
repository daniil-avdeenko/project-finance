"""
Точка входа планировщика.

Запускается отдельно от Flask:
    python -m scheduler.runner
"""

import asyncio
import contextlib
import logging
import os
import sys
from pathlib import Path

from aiohttp import web
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


async def _start_healthcheck_server() -> web.AppRunner | None:
    """
    Поднимает HTTP-сервер для healthcheck.

    Railway/Docker шлют GET /healthz → 200 OK. Без БД, без scheduler —
    просто «процесс отвечает».
    """
    if os.getenv("HEALTHCHECK_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return None

    port = int(os.getenv("HEALTHCHECK_PORT", "8080"))

    async def healthz(_request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    app = web.Application()
    app.router.add_get("/healthz", healthz)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info("Healthcheck listening on :%d/healthz", port)
    return runner


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

    healthcheck_runner = await _start_healthcheck_server()

    try:
        await asyncio.Event().wait()  # ждём вечно
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown signal received")
    finally:
        scheduler.shutdown(wait=True)
        if healthcheck_runner:
            await healthcheck_runner.cleanup()
        logger.info("Scheduler stopped")


def main() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run())


if __name__ == "__main__":
    main()
