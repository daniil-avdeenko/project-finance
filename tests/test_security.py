"""Тесты security-фич."""

import pytest


def test_healthz_returns_ok_without_login(client):
    """Healthcheck доступен без логина и возвращает 200 JSON."""
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_secret_key_required_in_production(monkeypatch):
    """В production без SECRET_KEY приложение не стартует."""
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    from app import create_app

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()


def test_secret_key_dev_fallback(monkeypatch):
    """В development без SECRET_KEY используется dev-значение."""
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    from app import create_app

    app = create_app()
    assert app.config["SECRET_KEY"] == "dev-key-for-testing"
