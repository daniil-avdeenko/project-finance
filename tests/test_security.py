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
    """Все ключевые security headers присутствуют в ответе."""
    response = client.get("/healthz")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "strict-origin-when-cross-origin" in response.headers["Referrer-Policy"]
    assert "geolocation=()" in response.headers["Permissions-Policy"]
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_csp_omits_upgrade_in_dev(client):
    """В dev (HTTP, SESSION_COOKIE_SECURE=false) upgrade-insecure-requests нет."""
    response = client.get("/healthz")

    assert "upgrade-insecure-requests" not in response.headers["Content-Security-Policy"]


def test_csp_adds_upgrade_in_https_mode(app):
    """В HTTPS-режиме (SESSION_COOKIE_SECURE=true) upgrade-insecure-requests возвращается."""
    app.config["SESSION_COOKIE_SECURE"] = True
    client = app.test_client()

    response = client.get("/healthz")

    assert "upgrade-insecure-requests" in response.headers["Content-Security-Policy"]


def test_headers_on_login_page(client):
    """Headers добавляются и к HTML-страницам, не только к JSON."""
    response = client.get("/login")
    assert "X-Content-Type-Options" in response.headers


def test_login_rate_limit(monkeypatch, tmp_path):
    """6 POST-попыток логина с одного IP → 429."""
    monkeypatch.setenv("RATELIMIT_ENABLED", "true")
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")

    from app import create_app
    from app import db as _db
    from app.models import User

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    with app.app_context():
        _db.create_all()
        user = User(username="x", role="user")
        user.set_password("real")
        _db.session.add(user)
        _db.session.commit()

    client = app.test_client()

    for i in range(5):
        response = client.post("/login", data={"username": "x", "password": "wrong"})
        assert response.status_code in (200, 302), f"Попытка {i + 1}"

    response = client.post("/login", data={"username": "x", "password": "wrong"})
    assert response.status_code == 429


def test_429_returns_custom_page(monkeypatch, tmp_path):
    """При превышении лимита возвращается кастомная страница."""
    monkeypatch.setenv("RATELIMIT_ENABLED", "true")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'rl.db'}")

    from app import create_app
    from app import db as _db
    from app.models import User

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    with app.app_context():
        _db.create_all()
        u = User(username="x", role="user")
        u.set_password("real")
        _db.session.add(u)
        _db.session.commit()

    client = app.test_client()
    for _ in range(5):
        client.post("/login", data={"username": "x", "password": "wrong"})

    response = client.post("/login", data={"username": "x", "password": "wrong"})
    assert response.status_code == 429
    assert "Слишком много попыток" in response.get_data(as_text=True)


def test_sanitize_plain_token():
    from app.security import sanitize_secrets

    cleaned = sanitize_secrets("TOKEN=abc123xyz")
    assert "abc123xyz" not in cleaned
    assert "***" in cleaned


def test_sanitize_quoted_secret():
    from app.security import sanitize_secrets

    cleaned = sanitize_secrets('SECRET_KEY: "my-secret-value"')
    assert "my-secret-value" not in cleaned


def test_sanitize_bearer():
    from app.security import sanitize_secrets

    cleaned = sanitize_secrets("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig")
    assert "eyJhbGci" not in cleaned
    assert "Bearer" in cleaned


def test_sanitize_telegram_token():
    from app.security import sanitize_secrets

    cleaned = sanitize_secrets("token 1234567890:AAHfghjkLmnopQrstUvwxYz1234567890_-")
    assert "1234567890:AAH" not in cleaned


def test_sanitize_preserves_normal_text():
    from app.security import sanitize_secrets

    text = "Ошибка: файл не найден"
    assert sanitize_secrets(text) == text


def test_sanitize_empty_string():
    from app.security import sanitize_secrets

    assert sanitize_secrets("") == ""


def test_proxy_fix_wraps_wsgi_app(app):
    """ProxyFix обёрнут вокруг wsgi_app — иначе X-Forwarded-* не применяются."""
    from werkzeug.middleware.proxy_fix import ProxyFix

    assert isinstance(app.wsgi_app, ProxyFix)
