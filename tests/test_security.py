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


def test_security_headers_present(client):
    """Все ключевые headers присутствуют в ответе."""
    response = client.get("/healthz")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "strict-origin-when-cross-origin" in response.headers["Referrer-Policy"]
    assert "geolocation=()" in response.headers["Permissions-Policy"]
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_headers_on_login_page(client):
    """Headers добавляются и к HTML-страницам, не только к JSON."""
    response = client.get("/login")
    assert "X-Content-Type-Options" in response.headers
