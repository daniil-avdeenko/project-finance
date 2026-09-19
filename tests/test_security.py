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
