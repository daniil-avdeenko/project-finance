"""
Сервис логирования синхронизаций.

Каждый вызов внешнего API (Grist, Google Sheets) фиксируется в БД:
статус, количество записей, текст ошибки. Дашборд показывает
время последней успешной синхронизации.
"""

import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app import db
from app.models import SyncLog

logger = logging.getLogger(__name__)


def log_sync(
    sync_type: str,
    status: str,
    records_count: int | None = None,
    error: str | None = None,
) -> SyncLog:
    """Записывает результат синхронизации в БД."""
    entry = SyncLog(
        sync_type=sync_type,
        status=status,
        records_count=records_count,
        error_message=error,
    )
    db.session.add(entry)
    db.session.commit()
    logger.debug("SyncLog: %s %s records=%s", sync_type, status, records_count)
    return entry


def get_last_sync(sync_type: str) -> SyncLog | None:
    """Возвращает последнюю запись о синхронизации данного типа."""
    return SyncLog.query.filter_by(sync_type=sync_type).order_by(SyncLog.synced_at.desc()).first()


# Часовой пояс для отображения. Хранится в UTC, показывается в MSK.
DISPLAY_TZ = ZoneInfo("Europe/Moscow")


def format_sync_time(dt: datetime | None, fmt: str = "%d.%m %H:%M") -> str:
    """
    Форматирует UTC-время из БД в локальное (Europe/Moscow).

    SQLite возвращает naive datetime — считаем её UTC.
    """
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(DISPLAY_TZ).strftime(fmt)
