"""Тесты ручной синхронизации и отображения статуса."""

from unittest.mock import AsyncMock, patch

from app import db as _db
from app.models import SyncLog
from app.services.sync_service import get_last_sync, log_sync

# ============================================================
#   SyncLog + сервис
# ============================================================


def test_log_sync_success(app):
    with app.app_context():
        entry = log_sync("grist", "success", records_count=10)

        assert entry.id is not None
        assert entry.sync_type == "grist"
        assert entry.status == "success"
        assert entry.records_count == 10
        assert entry.error_message is None


def test_log_sync_error(app):
    with app.app_context():
        entry = log_sync("sheets", "error", error="timeout")

        assert entry.status == "error"
        assert entry.error_message == "timeout"


def test_get_last_sync_returns_latest(app):
    with app.app_context():
        log_sync("grist", "success", records_count=1)
        log_sync("grist", "success", records_count=2)

        last = get_last_sync("grist")
        assert last.records_count == 2


def test_get_last_sync_empty(app):
    with app.app_context():
        assert get_last_sync("grist") is None


# ============================================================
#   Роут /sync/grist
# ============================================================


def test_sync_grist_forbidden_for_regular_user(regular_client):
    response = regular_client.post("/sync/grist", follow_redirects=False)
    assert response.status_code == 302


def test_sync_grist_requires_login(client):
    response = client.post("/sync/grist", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.location


def test_sync_grist_success(auth_client, app):
    """Роут синхронизирует Grist и логирует успех."""
    with (
        patch(
            "app.integrations.grist_httpx.sync_projects_to_grist_httpx",
            new=AsyncMock(return_value={"added": 1, "updated": 0, "deleted": 0}),
        ),
        patch(
            "app.integrations.grist_httpx.sync_transactions_to_grist_httpx",
            new=AsyncMock(return_value={"added": 5, "updated": 0, "deleted": 0}),
        ),
    ):
        response = auth_client.post("/sync/grist", follow_redirects=True)

    assert response.status_code == 200

    with app.app_context():
        log = get_last_sync("grist")
        assert log is not None
        assert log.status == "success"
        assert log.records_count == 6  # 1 + 5


def test_sync_grist_error(auth_client, app):
    """Ошибка в Grist логируется как error, Sheets-лог не трогается."""
    with (
        patch(
            "app.integrations.grist_httpx.sync_projects_to_grist_httpx",
            new=AsyncMock(side_effect=RuntimeError("grist down")),
        ),
        patch(
            "app.integrations.grist_httpx.sync_transactions_to_grist_httpx",
            new=AsyncMock(return_value={"added": 0, "updated": 0, "deleted": 0}),
        ),
    ):
        response = auth_client.post("/sync/grist", follow_redirects=True)

    assert response.status_code == 200

    with app.app_context():
        assert get_last_sync("grist").status == "error"
        # Sheets-лог не должен появиться — синхронизация Sheets не вызывалась
        assert get_last_sync("sheets") is None


# ============================================================
#   Роут /sync/sheets
# ============================================================


def test_sync_sheets_forbidden_for_regular_user(regular_client):
    response = regular_client.post("/sync/sheets", follow_redirects=False)
    assert response.status_code == 302


def test_sync_sheets_requires_login(client):
    response = client.post("/sync/sheets", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.location


def test_sync_sheets_success(auth_client, app):
    with patch(
        "app.integrations.google_sheets.sync_all_to_sheets",
        return_value={"projects": 6, "transactions": 100},
    ):
        response = auth_client.post("/sync/sheets", follow_redirects=True)

    assert response.status_code == 200

    with app.app_context():
        log = get_last_sync("sheets")
        assert log is not None
        assert log.status == "success"
        assert log.records_count == 106  # 6 + 100


def test_sync_sheets_error(auth_client, app):
    with patch(
        "app.integrations.google_sheets.sync_all_to_sheets",
        side_effect=RuntimeError("sheets api down"),
    ):
        response = auth_client.post("/sync/sheets", follow_redirects=True)

    assert response.status_code == 200

    with app.app_context():
        assert get_last_sync("sheets").status == "error"
        # Grist-лог не должен появиться
        assert get_last_sync("grist") is None


# ============================================================
#   Дашборд: кнопки, ссылки, время
# ============================================================


def test_dashboard_shows_sync_times(auth_client, app):
    """Время синхронизации отображается в формате `DD.MM HH:MM`."""
    import re

    with app.app_context():
        log_sync("grist", "success", records_count=1)

    response = auth_client.get("/")
    text = response.get_data(as_text=True)

    # Дата-время в формате «22.09 15:30»
    assert re.search(r"\d{2}\.\d{2} \d{2}:\d{2}", text)
    # Tooltip содержит название сервиса
    assert "Grist:" in text


def test_dashboard_shows_both_sync_buttons_for_admin(auth_client):
    response = auth_client.get("/")
    text = response.get_data(as_text=True)
    assert "/sync/grist" in text
    assert "/sync/sheets" in text


def test_dashboard_hides_sync_buttons_for_user(regular_client):
    response = regular_client.get("/")
    text = response.get_data(as_text=True)
    assert "/sync/grist" not in text
    assert "/sync/sheets" not in text


# ============================================================
#   format_sync_time — конвертация UTC → MSK
# ============================================================


def test_format_sync_time_converts_utc_to_msk():
    """UTC 12:00 → MSK 15:00."""
    from datetime import UTC, datetime

    from app.services.sync_service import format_sync_time

    utc_dt = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    assert format_sync_time(utc_dt) == "22.09 15:00"


def test_format_sync_time_handles_naive_datetime():
    """Naive datetime считается UTC (как возвращает SQLite)."""
    from datetime import datetime

    from app.services.sync_service import format_sync_time

    naive = datetime(2026, 9, 22, 12, 0)
    assert format_sync_time(naive) == "22.09 15:00"


def test_format_sync_time_none():
    """None → тире."""
    from app.services.sync_service import format_sync_time

    assert format_sync_time(None) == "—"


def test_dashboard_renders_msk_time(auth_client, app):
    """Время последней синхронизации на дашборде — в MSK."""
    from datetime import UTC, datetime

    with app.app_context():
        entry = SyncLog(
            sync_type="grist",
            status="success",
            synced_at=datetime(2026, 9, 22, 12, 0, tzinfo=UTC),
        )
        _db.session.add(entry)
        _db.session.commit()

    response = auth_client.get("/")
    text = response.get_data(as_text=True)
    assert "22.09 15:00" in text
    assert "22.09 12:00" not in text
