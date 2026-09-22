"""
Сервис логирования синхронизаций.

Каждый вызов внешнего API (Grist, Google Sheets) фиксируется в БД:
статус, количество записей, текст ошибки. Дашборд показывает
время последней успешной синхронизации.
"""

import logging

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
