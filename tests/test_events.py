"""Тесты event-driven: listeners и запись в event_log."""

import pytest

from app import db as _db
from app.models import EventLog, IncomeCategory, Project, Transaction


@pytest.fixture(autouse=True)
def enable_events(monkeypatch):
    """Включаем эмиссию событий для всех тестов в этом файле."""
    monkeypatch.setenv("EVENTS_ENABLED", "true")


def test_project_insert_creates_event(app):
    """INSERT Project → одна запись в event_log с типом project_created."""
    with app.app_context():
        project = Project(name="Тестовый проект", description="Описание")
        _db.session.add(project)
        _db.session.commit()

        events = EventLog.query.all()
        assert len(events) == 1

        event = events[0]
        assert event.event_type == "project_created"
        assert event.status == "pending"
        assert event.attempts == 0
        assert event.payload["id"] == project.id
        assert event.payload["name"] == "Тестовый проект"
        assert event.payload["description"] == "Описание"


def test_transaction_insert_creates_event(app):
    """INSERT Transaction → событие с деталями транзакции и именем проекта."""
    with app.app_context():
        project = Project(name="CRM для банка")
        category = IncomeCategory(name="Разработка")
        _db.session.add_all([project, category])
        _db.session.commit()

        # Проект уже создал одно событие, очистим для чистоты теста
        EventLog.query.delete()
        _db.session.commit()

        transaction = Transaction(
            project_id=project.id,
            type="income",
            category_id=category.id,
            amount=500000,
            currency="RUB",
            description="Оплата по договору",
        )
        _db.session.add(transaction)
        _db.session.commit()

        events = EventLog.query.all()
        assert len(events) == 1

        event = events[0]
        assert event.event_type == "transaction_created"
        assert event.payload["id"] == transaction.id
        assert event.payload["project_id"] == project.id
        assert event.payload["project_name"] == "CRM для банка"
        assert event.payload["type"] == "income"
        assert event.payload["amount"] == 500000
        assert event.payload["currency"] == "RUB"
        assert event.payload["description"] == "Оплата по договору"


def test_events_disabled_via_env(app, monkeypatch):
    """При EVENTS_ENABLED=false события не создаются."""
    monkeypatch.setenv("EVENTS_ENABLED", "false")

    with app.app_context():
        project = Project(name="Без событий")
        _db.session.add(project)
        _db.session.commit()

        assert EventLog.query.count() == 0


def test_event_rollback_with_transaction(app, monkeypatch):
    """Если INSERT откатывается — событие тоже откатывается."""
    monkeypatch.setenv("EVENTS_ENABLED", "true")

    with app.app_context():
        project = Project(name="Откатываемый")
        _db.session.add(project)
        _db.session.rollback()

        assert EventLog.query.count() == 0
        assert Project.query.count() == 0
