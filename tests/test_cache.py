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
def reset_cache_state(monkeypatch):
    """
    Сбрасывает глобальное состояние app.cache перед тестом.
    """
    import app.cache

    monkeypatch.setattr(app.cache, "_client", None)
    monkeypatch.setattr(app.cache, "_client_unavailable", False)
    yield
    monkeypatch.setattr(app.cache, "_client", None)
    monkeypatch.setattr(app.cache, "_client_unavailable", True)


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


def test_cache_module_returns_none_on_unreachable_redis(monkeypatch, reset_cache_state):
    """get_cache возвращает None, если Redis недоступен — приложение не падает."""
    import app.cache

    def raising_from_url(*args, **kwargs):
        raise app.cache.redis.RedisError("connection refused")

    monkeypatch.setattr(app.cache.redis, "from_url", raising_from_url)

    cache = app.cache.get_cache()

    assert cache is None
    assert app.cache._client_unavailable is True


def test_cache_module_does_not_retry_after_failure(monkeypatch, reset_cache_state):
    """После первого провала get_cache не пытается снова — иначе каждый запрос ждёт таймаут."""
    import app.cache

    calls = {"count": 0}

    def counting_from_url(*args, **kwargs):
        calls["count"] += 1
        raise app.cache.redis.RedisError("connection refused")

    monkeypatch.setattr(app.cache.redis, "from_url", counting_from_url)

    app.cache.get_cache()
    app.cache.get_cache()
    app.cache.get_cache()

    assert calls["count"] == 1  # попытка подключения была только одна


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


def test_get_rates_map_falls_back_when_redis_dies(app, monkeypatch):
    """
    Redis был доступен, потом упал — get_rates_map переключается на БД.

    Регресс: раньше _client_unavailable срабатывал только при первичном
    подключении. Если клиент уже создан, get_cache() возвращал его,
    и каждый запрос платил socket_timeout при попытке cache.get().
    """
    from datetime import date

    import redis as redis_lib

    from app import cache as cache_module

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache_module, "_client", fake)
    monkeypatch.setattr(cache_module, "_client_unavailable", False)
    monkeypatch.setattr(currency_service, "get_cache", cache_module.get_cache)
    monkeypatch.setattr(
        currency_service, "mark_cache_unavailable", cache_module.mark_cache_unavailable
    )

    with app.app_context():
        upsert_rates([FakeRate("USD", 1, 84.5, date(2026, 9, 19))])

        # Первый запрос — кэш заполняется через fakeredis
        result1 = get_rates_map({"USD"})
        assert result1["USD"][0].rate_rub == 84.5
        assert fake.exists("rates_map:USD") == 1

        # «Ломаем» fakeredis — теперь get/setex падают
        def raising_get(*args, **kwargs):
            raise redis_lib.ConnectionError("redis is dead")

        def raising_setex(*args, **kwargs):
            raise redis_lib.ConnectionError("redis is dead")

        monkeypatch.setattr(fake, "get", raising_get)
        monkeypatch.setattr(fake, "setex", raising_setex)

        # Второй запрос — падение Redis ловится, идёт fallback на БД
        result2 = get_rates_map({"USD"})
        assert result2["USD"][0].rate_rub == 84.5

        # Клиент помечен как недоступный — get_cache() возвращает None
        assert cache_module._client_unavailable is True
        assert cache_module.get_cache() is None

        # Третий запрос — уже без Redis, только БД
        result3 = get_rates_map({"USD"})
        assert result3["USD"][0].rate_rub == 84.5
