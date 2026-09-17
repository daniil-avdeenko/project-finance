"""
Event-driven
SQLAlchemy listeners создают записи в event_log при INSERT Project/Transaction.
Scheduler читает pending и отправляет в Telegram.
"""

import logging
import os

from sqlalchemy import event, insert

from app.models import EventLog, Project, Transaction

logger = logging.getLogger(__name__)


def _events_enabled() -> bool:
    """Читает флаг на каждом вызове — удобно для тестов и seed."""
    return os.getenv("EVENTS_ENABLED", "true").lower() in ("1", "true", "yes")


def _emit(connection, event_type: str, payload: dict) -> None:
    """
    Записывает событие в event_log через low-level connection.
    """
    if not _events_enabled():
        return

    try:
        connection.execute(
            insert(EventLog).values(
                event_type=event_type,
                payload=payload,
                status="pending",
                attempts=0,
            )
        )
        logger.debug("Emitted event: %s", event_type)
    except Exception:
        # Никогда не роняем основной insert из-за ошибки в listener
        logger.exception("Failed to emit event %s", event_type)


@event.listens_for(Project, "after_insert")
def on_project_insert(mapper, connection, target: Project) -> None:
    """Эмитит событие при создании проекта."""
    _emit(
        connection,
        "project_created",
        {
            "id": target.id,
            "name": target.name,
            "description": target.description or "",
        },
    )


@event.listens_for(Transaction, "after_insert")
def on_transaction_insert(mapper, connection, target: Transaction) -> None:
    """
    Эмитит событие при создании транзакции.
    """
    row = connection.execute(
        Project.__table__.select().where(Project.__table__.c.id == target.project_id)
    ).first()
    project_name = row.name if row else "—"

    _emit(
        connection,
        "transaction_created",
        {
            "id": target.id,
            "project_id": target.project_id,
            "project_name": project_name,
            "type": target.type,
            "amount": target.amount,
            "currency": target.currency or "RUB",
            "description": target.description or "",
            "date": target.date.isoformat() if target.date else None,
        },
    )
