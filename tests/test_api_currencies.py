"""Тесты публичного API: курсы валют."""

from datetime import UTC, date, datetime

from app import db as _db
from app.models import CurrencyRate


def test_currencies_empty(client):
    """Без данных — пустой объект rates."""
    response = client.get("/api/v1/currencies")

    assert response.status_code == 200
    data = response.get_json()
    assert data["rates"] == {}


def test_currencies_returns_latest(client, app):
    """Возвращает самый свежий курс на каждую валюту."""
    with app.app_context():
        _db.session.add_all(
            [
                CurrencyRate(code="USD", rate_date=date(2026, 9, 20), nominal=1, rate_rub=84.0),
                CurrencyRate(code="USD", rate_date=date(2026, 9, 22), nominal=1, rate_rub=85.5),
                CurrencyRate(code="EUR", rate_date=date(2026, 9, 22), nominal=1, rate_rub=97.2),
            ]
        )
        _db.session.commit()

    response = client.get("/api/v1/currencies")

    assert response.status_code == 200
    data = response.get_json()
    assert data["rates"]["USD"]["rate_rub"] == 85.5
    assert data["rates"]["USD"]["rate_date"] == "2026-09-22"
    assert data["rates"]["EUR"]["rate_rub"] == 97.2


def test_currencies_ignores_other_codes(client, app):
    """Возвращает только USD и EUR."""
    with app.app_context():
        _db.session.add_all(
            [
                CurrencyRate(code="USD", rate_date=date(2026, 9, 22), nominal=1, rate_rub=85.5),
                CurrencyRate(code="JPY", rate_date=date(2026, 9, 22), nominal=100, rate_rub=54.12),
            ]
        )
        _db.session.commit()

    response = client.get("/api/v1/currencies")
    data = response.get_json()

    assert "USD" in data["rates"]
    assert "JPY" not in data["rates"]
