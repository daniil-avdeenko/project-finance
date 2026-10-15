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
        return_value={"projects": 6, "transactions": 100, "rates": 3},
    ):
        response = auth_client.post("/sync/sheets", follow_redirects=True)

    assert response.status_code == 200

    with app.app_context():
        log = get_last_sync("sheets")
        assert log is not None
        assert log.status == "success"
        assert log.records_count == 109  # 6 + 100 + 3
        assert "Google Sheets синхронизирован" in response.get_data(as_text=True)


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
        assert "Ошибка синхронизации Sheets" in response.get_data(as_text=True)


# ============================================================
#   Дашборд: кнопки, ссылки, время
# ============================================================


def test_dashboard_shows_sync_times(auth_client, app):
    """Время синхронизации отображается в формате `DD.MM HH:MM`."""
    import re

    with app.app_context():
        log_sync("sheets", "success", records_count=1)

    response = auth_client.get("/")
    text = response.get_data(as_text=True)

    assert re.search(r"\d{2}\.\d{2} \d{2}:\d{2}", text)
    assert "Sheets:" in text


def test_dashboard_shows_sync_button_for_admin(auth_client):
    response = auth_client.get("/")
    text = response.get_data(as_text=True)
    assert "/sync/sheets" in text


def test_dashboard_hides_sync_button_for_user(regular_client):
    response = regular_client.get("/")
    text = response.get_data(as_text=True)
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
            sync_type="sheets",
            status="success",
            synced_at=datetime(2026, 9, 22, 12, 0, tzinfo=UTC),
        )
        _db.session.add(entry)
        _db.session.commit()

    response = auth_client.get("/")
    text = response.get_data(as_text=True)
    assert "22.09 15:00" in text
    assert "22.09 12:00" not in text


def test_short_error_http_status():
    import httpx

    from app.services.sync_service import short_error

    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(401, request=request)
    err = httpx.HTTPStatusError("401", request=request, response=response)
    assert short_error(err) == "HTTP 401 — неверный API-ключ"


def test_short_error_500():
    import httpx

    from app.services.sync_service import short_error

    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(503, request=request)
    err = httpx.HTTPStatusError("503", request=request, response=response)
    assert short_error(err) == "HTTP 503 — сервис недоступен"


def test_short_error_request_error():
    import httpx

    from app.services.sync_service import short_error

    err = httpx.ConnectError("Connection refused")
    assert "сеть недоступна" in short_error(err)


def test_short_error_truncates_long_message():
    from app.services.sync_service import short_error

    err = RuntimeError("a" * 500)
    result = short_error(err)
    assert len(result) <= 121  # 120 + многоточие
    assert result.endswith("…")
