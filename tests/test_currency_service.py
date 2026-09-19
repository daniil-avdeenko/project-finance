"""Тесты сервиса курсов валют."""

from datetime import date

from app.models import CurrencyRate
from app.services.currency_service import (
    convert_to_rub,
    get_rate,
    upsert_rates,
)


class FakeRate:
    """Дублирует ScrapedRate — не подключаем Playwright."""

    def __init__(self, code: str, nominal: int, rate: float, rate_date: date):
        self.code = code
        self.nominal = nominal
        self.rate = rate
        self.rate_date = rate_date


# ============================================================
#   upsert_rates
# ============================================================


def test_upsert_rates_inserts_new(app):
    with app.app_context():
        rates = [
            FakeRate("USD", 1, 84.50, date(2026, 9, 19)),
            FakeRate("EUR", 1, 97.50, date(2026, 9, 19)),
        ]
        result = upsert_rates(rates)

        assert result == {"added": 2, "updated": 0}
        assert CurrencyRate.query.count() == 2


def test_upsert_rates_updates_existing(app):
    """Повторный upsert на ту же дату обновляет, а не создаёт дубликат."""
    with app.app_context():
        upsert_rates([FakeRate("USD", 1, 84.50, date(2026, 9, 19))])
        result = upsert_rates([FakeRate("USD", 1, 85.00, date(2026, 9, 19))])

        assert result == {"added": 0, "updated": 1}
        assert CurrencyRate.query.count() == 1
        assert CurrencyRate.query.one().rate_rub == 85.00


def test_upsert_rates_different_dates_are_separate_rows(app):
    with app.app_context():
        upsert_rates(
            [
                FakeRate("USD", 1, 84.50, date(2026, 9, 18)),
                FakeRate("USD", 1, 85.00, date(2026, 9, 19)),
            ]
        )
        assert CurrencyRate.query.count() == 2


# ============================================================
#   get_rate
# ============================================================


def test_get_rate_returns_latest_when_no_date(app):
    with app.app_context():
        upsert_rates(
            [
                FakeRate("USD", 1, 84.00, date(2026, 9, 18)),
                FakeRate("USD", 1, 85.00, date(2026, 9, 19)),
            ]
        )
        rate = get_rate("USD")
        assert rate is not None
        assert rate.rate_rub == 85.00


def test_get_rate_returns_exact_date(app):
    with app.app_context():
        upsert_rates([FakeRate("USD", 1, 84.00, date(2026, 9, 18))])
        rate = get_rate("USD", date(2026, 9, 18))
        assert rate is not None
        assert rate.rate_rub == 84.00


def test_get_rate_falls_back_to_previous(app):
    """Нет курса на дату — берём ближайший предыдущий."""
    with app.app_context():
        upsert_rates(
            [
                FakeRate("USD", 1, 84.00, date(2026, 9, 18)),
                FakeRate("USD", 1, 85.00, date(2026, 9, 20)),
            ]
        )
        # 19 сентября нет — должен вернуться 18-е
        rate = get_rate("USD", date(2026, 9, 19))
        assert rate is not None
        assert rate.rate_rub == 84.00


def test_get_rate_returns_none_for_unknown_currency(app):
    with app.app_context():
        assert get_rate("XXX") is None


def test_get_rate_returns_none_when_all_dates_are_future(app):
    """Если все курсы позже запрошенной даты — None."""
    with app.app_context():
        upsert_rates([FakeRate("USD", 1, 84.00, date(2026, 9, 20))])
        assert get_rate("USD", date(2026, 9, 19)) is None


# ============================================================
#   convert_to_rub
# ============================================================


def test_convert_rub_returns_same_amount(app):
    with app.app_context():
        assert convert_to_rub(1000, "RUB") == 1000


def test_convert_empty_currency_treated_as_rub(app):
    with app.app_context():
        assert convert_to_rub(500, "") == 500


def test_convert_usd_uses_rate(app):
    with app.app_context():
        upsert_rates([FakeRate("USD", 1, 84.50, date(2026, 9, 19))])
        result = convert_to_rub(100, "USD", date(2026, 9, 19))
        assert result == 8450.0


def test_convert_nominal_greater_than_one(app):
    """JPY: nominal=100, значит курс за 100 йен."""
    with app.app_context():
        upsert_rates([FakeRate("JPY", 100, 54.12, date(2026, 9, 19))])
        result = convert_to_rub(1000, "JPY", date(2026, 9, 19))
        # 1000 йен = 10 * nominal → 10 * 54.12
        assert result == 541.20


def test_convert_unknown_currency_returns_original(app):
    """Нет курса — возвращаем исходную сумму (graceful degradation)."""
    with app.app_context():
        assert convert_to_rub(100, "XXX") == 100


def test_convert_rounds_to_two_decimals(app):
    with app.app_context():
        upsert_rates([FakeRate("USD", 1, 84.5678, date(2026, 9, 19))])
        result = convert_to_rub(123.45, "USD", date(2026, 9, 19))
        # 123.45 * 84.5678 = 10439.894... → 10439.89
        assert result == 10439.89
