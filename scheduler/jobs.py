"""
Задачи планировщика.

Все job'ы — async-функции, принимают Flask-app как первый аргумент.
Ошибки не поднимаются наружу (кроме CancelledError при shutdown) —
APScheduler не должен снимать job из-за одного падения.
"""

import asyncio
import logging
import traceback as tb_module
from datetime import UTC, datetime
from html import escape

from sqlalchemy.orm import joinedload

from app import db
from app.integrations.telegram import send_message
from app.models import EventLog, Project, Transaction

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
MAX_ITEMS_PER_GROUP = 5


# ============================================================
#   ФОРМАТИРОВАНИЕ DIGEST
# ============================================================


def _format_digest(events: list[EventLog]) -> str:
    """Собирает один HTML-текст из списка событий, группируя по типу."""
    by_type: dict[str, list[EventLog]] = {}
    for e in events:
        by_type.setdefault(e.event_type, []).append(e)

    parts = ["📬 <b>События</b>"]

    if "project_created" in by_type:
        items = by_type["project_created"]
        parts.append("")
        parts.append(f"🆕 <b>Новые проекты ({len(items)}):</b>")
        for e in items[:MAX_ITEMS_PER_GROUP]:
            parts.append(f"• {escape(e.payload.get('name', '—'))}")
        if len(items) > MAX_ITEMS_PER_GROUP:
            parts.append(f"• и ещё {len(items) - MAX_ITEMS_PER_GROUP}")

    if "transaction_created" in by_type:
        items = by_type["transaction_created"]
        parts.append("")
        parts.append(f"💰 <b>Новые транзакции ({len(items)}):</b>")
        for e in items[:MAX_ITEMS_PER_GROUP]:
            p = e.payload
            icon = "💸" if p.get("type") == "expense" else "💰"
            amount = f"{p.get('amount', 0):,.0f}".replace(",", " ")
            currency = p.get("currency", "RUB")
            project = escape(p.get("project_name", "—"))
            parts.append(f"{icon} {amount} {currency} — {project}")
        if len(items) > MAX_ITEMS_PER_GROUP:
            parts.append(f"• и ещё {len(items) - MAX_ITEMS_PER_GROUP}")

    if "error" in by_type:
        for e in by_type["error"]:
            p = e.payload
            parts.append("")
            parts.append(
                f"❌ <b>Ошибка в задаче</b> <code>{escape(p.get('task_name', '—'))}</code>"
            )
            parts.append(
                f"{escape(p.get('error_type', '—'))}: {escape(p.get('error_message', '—'))}"
            )

    return "\n".join(parts)


# ============================================================
#   JOB: обработка очереди событий
# ============================================================


async def job_process_events(app) -> None:
    """Раз в 30 секунд: читает pending EventLog и шлёт digest в Telegram."""
    with app.app_context():
        events = (
            EventLog.query.filter(EventLog.status == "pending")
            .filter(EventLog.attempts < MAX_ATTEMPTS)
            .order_by(EventLog.created_at.asc())
            .limit(100)
            .all()
        )

        if not events:
            return

        text = _format_digest(events)
        ok = await send_message(text)

        now = datetime.now(UTC)

        if ok:
            for e in events:
                e.status = "sent"
                e.sent_at = now
            logger.info("Sent digest with %d events", len(events))
        else:
            for e in events:
                e.attempts += 1
                e.last_error = "send_message returned False"
                if e.attempts >= MAX_ATTEMPTS:
                    e.status = "failed"
            logger.warning("Failed to send digest, attempts incremented for %d events", len(events))

        try:
            db.session.commit()
        except asyncio.CancelledError:
            logger.info("job_process_events отменён (shutdown)")
            raise
        except Exception:
            db.session.rollback()
            logger.exception("Failed to update event statuses")


# ============================================================
#   JOB: healthcheck
# ============================================================


async def job_healthcheck(app) -> None:
    """Раз в 6 часов: прямое сообщение в Telegram (без очереди)."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    text = f"💚 <b>Планировщик работает исправно</b>\n\n{now}"
    await send_message(text)


# ============================================================
#   JOB: scrape_cbr
# ============================================================


async def job_scrape_cbr(app) -> None:
    """Раз в 6 часов: парсит курсы ЦБ и сохраняет в БД."""
    with app.app_context():
        from app.integrations.cbr_scraper import scrape_cbr_rates
        from app.services.currency_service import upsert_rates

        try:
            rates = await scrape_cbr_rates()
            if not rates:
                logger.warning("job_scrape_cbr: пустой результат парсинга")
                return

            result = upsert_rates(rates)
            logger.info(
                "job_scrape_cbr: added=%d, updated=%d",
                result["added"],
                result["updated"],
            )

        except asyncio.CancelledError:
            logger.info("job_scrape_cbr отменён (shutdown)")
            raise
        except Exception as e:
            logger.exception("job_scrape_cbr failed")
            db.session.rollback()
            db.session.add(
                EventLog(
                    event_type="error",
                    payload={
                        "task_name": "job_scrape_cbr",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "traceback": tb_module.format_exc()[-1500:],
                    },
                    status="pending",
                )
            )
            db.session.commit()


# ============================================================
#   JOB: sync_sheets
# ============================================================


async def job_sync_sheets(app) -> None:
    """Раз в час: экспорт проектов, транзакций и курсов в Google Sheets."""
    with app.app_context():
        from app.integrations.google_sheets import sync_all_to_sheets
        from app.services.currency_service import get_latest_rates
        from app.services.sync_service import log_sync

        try:
            projects = Project.active().all()
            transactions = (
                Transaction.active()
                .options(joinedload(Transaction.project))
                .order_by(Transaction.date.desc())
                .all()
            )
            rates = get_latest_rates({"USD", "EUR", "CNY"})

            # gspread синхронный — уводим в отдельный поток
            result = await asyncio.to_thread(sync_all_to_sheets, projects, transactions, rates)
            total = result["projects"] + result["transactions"] + result["rates"]
            log_sync("sheets", "success", records_count=total)
            logger.info(
                "job_sync_sheets: %d проектов, %d транзакций, %d курсов",
                result["projects"],
                result["transactions"],
                result["rates"],
            )

        except asyncio.CancelledError:
            logger.info("job_sync_sheets отменён (shutdown)")
            raise
        except Exception as e:
            logger.exception("job_sync_sheets failed")
            db.session.rollback()
            log_sync("sheets", "error", error=str(e)[:500])
            db.session.add(
                EventLog(
                    event_type="error",
                    payload={
                        "task_name": "job_sync_sheets",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "traceback": tb_module.format_exc()[-1500:],
                    },
                    status="pending",
                )
            )
            db.session.commit()
