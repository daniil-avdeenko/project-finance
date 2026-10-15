"""Тесты задач планировщика."""

from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from app import db as _db
from app.integrations.cbr_scraper import ScrapedRate  # noqa: F401
from app.models import EventLog, Project
from scheduler.jobs import (
    _format_digest,
    job_healthcheck,
    job_process_events,
    job_scrape_cbr,
)

SEND_URL = "https://api.telegram.org/bottest-token-123/sendMessage"


@pytest.fixture(autouse=True)
def telegram_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token-123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")
    monkeypatch.setenv("EVENTS_ENABLED", "true")


# ---------- _format_digest ----------


def test_format_digest_empty():
    assert "События" in _format_digest([])


def test_format_digest_groups_by_type(app):
    with app.app_context():
        e1 = EventLog(event_type="project_created", payload={"name": "A"})
        e2 = EventLog(event_type="project_created", payload={"name": "B"})
        e3 = EventLog(
            event_type="transaction_created",
            payload={"amount": 5000, "type": "income", "currency": "RUB", "project_name": "A"},
        )
        text = _format_digest([e1, e2, e3])

        assert "Новые проекты (2)" in text
        assert "• A" in text
        assert "• B" in text
        assert "Новые транзакции (1)" in text
        assert "5 000 RUB" in text


def test_format_digest_error(app):
    with app.app_context():
        e = EventLog(
            event_type="error",
            payload={"task_name": "job_test", "error_type": "ValueError", "error_message": "boom"},
        )
        text = _format_digest([e])
        assert "Ошибка" in text
        assert "job_test" in text
        assert "ValueError" in text


# ---------- job_process_events ----------


@respx.mock
async def test_process_events_sends_and_marks_sent(app):
    respx.post(SEND_URL).mock(return_value=httpx.Response(200, json={"ok": True}))

    with app.app_context():
        _db.session.add(EventLog(event_type="project_created", payload={"name": "X"}))
        _db.session.commit()

    await job_process_events(app)

    with app.app_context():
        e = EventLog.query.one()
        assert e.status == "sent"
        assert e.sent_at is not None
        assert e.attempts == 0


@respx.mock
async def test_process_events_increments_attempts_on_failure(app):
    respx.post(SEND_URL).mock(return_value=httpx.Response(500))

    with app.app_context():
        _db.session.add(EventLog(event_type="project_created", payload={"name": "X"}))
        _db.session.commit()

    await job_process_events(app)

    with app.app_context():
        e = EventLog.query.one()
        assert e.status == "pending"
        assert e.attempts == 1
        assert "False" in e.last_error


@respx.mock
async def test_process_events_marks_failed_after_max_attempts(app):
    respx.post(SEND_URL).mock(return_value=httpx.Response(500))

    with app.app_context():
        _db.session.add(
            EventLog(
                event_type="project_created",
                payload={"name": "X"},
                attempts=2,  # ещё один провал → failed
            )
        )
        _db.session.commit()

    await job_process_events(app)

    with app.app_context():
        e = EventLog.query.one()
        assert e.status == "failed"
        assert e.attempts == 3


async def test_process_events_no_pending(app):
    """Пустая очередь — выход без ошибок."""
    await job_process_events(app)  # должно просто пройти


# ---------- job_healthcheck ----------


@respx.mock
async def test_healthcheck_sends_message(app):
    route = respx.post(SEND_URL).mock(return_value=httpx.Response(200, json={"ok": True}))

    await job_healthcheck(app)

    assert route.called
    import json

    body = json.loads(route.calls.last.request.content)
    assert "Планировщик работает исправно" in body["text"]


# ---------- job_scrape_cbr ----------


async def test_scrape_cbr_job_success(app):
    """Успешный парсинг → upsert в БД, без error-события."""
    fake_rates = [
        ScrapedRate(code="USD", nominal=1, rate=84.50, rate_date=date(2026, 9, 19)),
        ScrapedRate(code="EUR", nominal=1, rate=97.50, rate_date=date(2026, 9, 19)),
        ScrapedRate(code="JPY", nominal=100, rate=54.12, rate_date=date(2026, 9, 19)),
    ]

    with patch(
        "app.integrations.cbr_scraper.scrape_cbr_rates",
        new=AsyncMock(return_value=fake_rates),
    ):
        await job_scrape_cbr(app)

    with app.app_context():
        from app.models import CurrencyRate

        assert CurrencyRate.query.count() == 3
        usd = CurrencyRate.query.filter_by(code="USD").one()
        assert usd.rate_rub == 84.50
        assert usd.nominal == 1

        assert EventLog.query.filter_by(event_type="error").count() == 0


async def test_scrape_cbr_job_empty_result_does_not_touch_db(app):
    """Пустой парсинг → ранний выход: БД пустая, ошибок нет."""
    with patch(
        "app.integrations.cbr_scraper.scrape_cbr_rates",
        new=AsyncMock(return_value=[]),
    ):
        await job_scrape_cbr(app)

    with app.app_context():
        from app.models import CurrencyRate

        assert CurrencyRate.query.count() == 0
        assert EventLog.query.filter_by(event_type="error").count() == 0


async def test_scrape_cbr_job_creates_error_event_on_failure(app):
    """Исключение в парсинге → error-событие в event_log."""
    with patch(
        "app.integrations.cbr_scraper.scrape_cbr_rates",
        new=AsyncMock(side_effect=RuntimeError("CBR unreachable")),
    ):
        await job_scrape_cbr(app)

    with app.app_context():
        events = EventLog.query.filter_by(event_type="error").all()
        assert len(events) == 1
        assert events[0].payload["task_name"] == "job_scrape_cbr"
        assert events[0].payload["error_type"] == "RuntimeError"
        assert "CBR unreachable" in events[0].payload["error_message"]
