"""
Задачи планировщика.
Все job'ы — async-функции, принимают Flask-app как первый аргумент.
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

    if "grist_sync_summary" in by_type:
        for e in by_type["grist_sync_summary"]:
            p = e.payload
            parts.append("")
            parts.append(
                f"🔄 <b>Grist sync:</b> +{p.get('projects_added', 0)} проектов, "
                f"+{p.get('transactions_added', 0)} транзакций"
            )

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
        except Exception:
            db.session.rollback()
            logger.exception("Failed to update event statuses")


# ============================================================
#   JOB: синхронизация с Grist
# ============================================================


async def job_sync_grist(app) -> None:
    """Раз в 30 минут: upsert Project/Transaction в Grist."""
    with app.app_context():
        # Локальный импорт — избегаем циклической зависимости при старте
        from app.integrations.grist_httpx import (
            sync_projects_to_grist_httpx,
            sync_transactions_to_grist_httpx,
        )

        try:
            projects = Project.active().all()
            transactions = (
                Transaction.active()
                .options(joinedload(Transaction.project))
                .order_by(Transaction.date.desc())
                .all()
            )

            p_result = await sync_projects_to_grist_httpx(projects)
            t_result = await sync_transactions_to_grist_httpx(transactions)

            added = p_result.get("added", 0) + t_result.get("added", 0)

            if added > 0:
                db.session.add(
                    EventLog(
                        event_type="grist_sync_summary",
                        payload={
                            "projects_added": p_result.get("added", 0),
                            "transactions_added": t_result.get("added", 0),
                            "projects_updated": p_result.get("updated", 0),
                            "transactions_updated": t_result.get("updated", 0),
                        },
                        status="pending",
                    )
                )
                db.session.commit()
                logger.info("Grist sync: added=%d", added)

        except Exception as e:
            db.session.rollback()
            logger.exception("job_sync_grist failed")
            # Ошибку тоже кладём в очередь — отправится следующим циклом process_events
            db.session.add(
                EventLog(
                    event_type="error",
                    payload={
                        "task_name": "job_sync_grist",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "traceback": tb_module.format_exc()[-1500:],
                    },
                    status="pending",
                )
            )
            db.session.commit()


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
    """Раз в 6 часов: парсит курсы ЦБ и сохраняет в БД + Grist."""
    with app.app_context():
        from app.integrations.cbr_scraper import scrape_cbr_rates
        from app.integrations.grist_httpx import sync_rates_to_grist_httpx
        from app.services.currency_service import upsert_rates

        try:
            rates = await scrape_cbr_rates()
            if not rates:
                logger.warning("job_scrape_cbr: пустой результат парсинга")
                return

            # 1. БД — источник истины для расчётов
            db_result = upsert_rates(rates)
            logger.info(
                "job_scrape_cbr DB: added=%d, updated=%d",
                db_result["added"],
                db_result["updated"],
            )

            # 2. Grist — витрина для команды (лог курсов)
            await sync_rates_to_grist_httpx(rates)
            logger.info("job_scrape_cbr Grist: получено %d курсов", len(rates))

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
    """Раз в час: экспорт проектов и транзакций в Google Sheets."""
    with app.app_context():
        from app.integrations.google_sheets import sync_all_to_sheets
        from app.models import Project, Transaction

        try:
            projects = Project.active().all()
            transactions = (
                Transaction.active()
                .options(joinedload(Transaction.project))
                .order_by(Transaction.date.desc())
                .all()
            )
            # gspread синхронный — уводим в отдельный поток
            result = await asyncio.to_thread(sync_all_to_sheets, projects, transactions)
            logger.info(
                "job_sync_sheets: %d проектов, %d транзакций",
                result["projects"],
                result["transactions"],
            )
        except Exception as e:
            logger.exception("job_sync_sheets failed")
            db.session.rollback()
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
