"""Тесты задач планировщика."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from app import db as _db
from app.models import EventLog, Project
from scheduler.jobs import _format_digest, job_healthcheck, job_process_events, job_sync_grist

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


# ---------- job_sync_grist ----------


@respx.mock
async def test_sync_grist_creates_summary_event_on_added(app):
    """Если в Grist что-то добавилось — создаётся summary-событие."""
    respx.post(SEND_URL).mock(return_value=httpx.Response(200, json={"ok": True}))

    with app.app_context():
        _db.session.add(Project(name="P1"))
        _db.session.commit()
        EventLog.query.delete()  # чистим событие от INSERT Project
        _db.session.commit()

    with (
        patch(
            "app.integrations.grist_httpx.sync_projects_to_grist_httpx",
            new=AsyncMock(return_value={"added": 1, "updated": 0}),
        ),
        patch(
            "app.integrations.grist_httpx.sync_transactions_to_grist_httpx",
            new=AsyncMock(return_value={"added": 0, "updated": 0}),
        ),
    ):
        await job_sync_grist(app)

    with app.app_context():
        events = EventLog.query.filter_by(event_type="grist_sync_summary").all()
        assert len(events) == 1
        assert events[0].payload["projects_added"] == 1


@respx.mock
async def test_sync_grist_no_summary_when_nothing_added(app):
    """Нет добавленных — нет summary-события."""
    with app.app_context():
        _db.session.add(Project(name="P1"))
        _db.session.commit()
        EventLog.query.delete()
        _db.session.commit()

    with (
        patch(
            "app.integrations.grist_httpx.sync_projects_to_grist_httpx",
            new=AsyncMock(return_value={"added": 0, "updated": 1}),
        ),
        patch(
            "app.integrations.grist_httpx.sync_transactions_to_grist_httpx",
            new=AsyncMock(return_value={"added": 0, "updated": 0}),
        ),
    ):
        await job_sync_grist(app)

    with app.app_context():
        assert EventLog.query.filter_by(event_type="grist_sync_summary").count() == 0


@respx.mock
async def test_sync_grist_creates_error_event_on_exception(app):
    """Ошибка sync → error-событие в очереди."""
    with app.app_context():
        _db.session.add(Project(name="P1"))
        _db.session.commit()
        EventLog.query.delete()
        _db.session.commit()

    with (
        patch(
            "app.integrations.grist_httpx.sync_projects_to_grist_httpx",
            new=AsyncMock(side_effect=ValueError("boom")),
        ),
        patch(
            "app.integrations.grist_httpx.sync_transactions_to_grist_httpx",
            new=AsyncMock(return_value={"added": 0, "updated": 0}),
        ),
    ):
        await job_sync_grist(app)

    with app.app_context():
        events = EventLog.query.filter_by(event_type="error").all()
        assert len(events) == 1
        assert events[0].payload["error_type"] == "ValueError"
        assert events[0].payload["task_name"] == "job_sync_grist"


# ---------- job_healthcheck ----------


@respx.mock
async def test_healthcheck_sends_message(app):
    route = respx.post(SEND_URL).mock(return_value=httpx.Response(200, json={"ok": True}))

    await job_healthcheck(app)

    assert route.called
    import json

    body = json.loads(route.calls.last.request.content)
    assert "Планировщик работает исправно" in body["text"]
