"""Тесты кэширования курсов валют через Redis (fakeredis)."""

import fakeredis
import pytest

from app.services import currency_service
from app.services.currency_service import get_rates_map, upsert_rates


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    """Подменяет реальный Redis на fakeredis для всех тестов в файле."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(currency_service, "get_cache", lambda: fake)
    return fake


@pytest.fixture
def reset_cache_client():
    """
    Сбрасывает глобальный _client до и после теста.
    """
    import app.cache

    app.cache._client = None
    yield
    app.cache._client = None


class FakeRate:
    def __init__(self, code, nominal, rate, rate_date):
        self.code = code
        self.nominal = nominal
        self.rate = rate
        self.rate_date = rate_date


def test_get_rates_map_caches_result(app, mock_redis):
    """Первый вызов идёт в БД, второй — из кэша."""
    from datetime import date

    with app.app_context():
        upsert_rates([FakeRate("USD", 1, 84.5, date(2026, 9, 19))])
        mock_redis.flushall()  # очищаем кэш после upsert

        result1 = get_rates_map({"USD"})
        assert "USD" in result1
        assert result1["USD"][0].rate_rub == 84.5
        assert result1["USD"][0].code == "USD"

        # Второй вызов должен взять из кэша — проверяем, что ключ есть
        assert mock_redis.exists("rates_map:USD") == 1

        result2 = get_rates_map({"USD"})
        assert result2["USD"][0].rate_rub == 84.5
        assert result2["USD"][0].rate_date == date(2026, 9, 19)


def test_get_rates_map_works_without_redis(app, monkeypatch):
    """Без Redis get_rates_map работает напрямую с БД."""
    from datetime import date

    monkeypatch.setattr(currency_service, "get_cache", lambda: None)

    with app.app_context():
        upsert_rates([FakeRate("EUR", 1, 97.0, date(2026, 9, 19))])

        result = get_rates_map({"EUR"})
        assert "EUR" in result
        assert result["EUR"][0].rate_rub == 97.0


def test_cache_module_returns_none_on_unreachable_redis(monkeypatch, reset_cache_client):
    """get_cache возвращает None, если Redis недоступен — приложение не падает."""
    import app.cache

    monkeypatch.setenv("REDIS_URL", "redis://invalid-host:9999/0")

    cache = app.cache.get_cache()

    assert cache is None
    assert app.cache._client is None


def test_upsert_rates_invalidates_cache(app, mock_redis):
    """После обновления курсов кэш должен сброситься."""
    from datetime import date

    with app.app_context():
        mock_redis.set("rates_map:USD", '{"USD": []}')
        mock_redis.set("rates_map:EUR", '{"EUR": []}')
        assert mock_redis.exists("rates_map:USD") == 1
        assert mock_redis.exists("rates_map:EUR") == 1

        upsert_rates([FakeRate("USD", 1, 85.0, date(2026, 9, 20))])

        assert mock_redis.exists("rates_map:USD") == 0
        assert mock_redis.exists("rates_map:EUR") == 0
