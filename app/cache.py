"""
Клиент Redis для кэширования.

Ленивая инициализация: соединение устанавливается при первом обращении.
Если Redis недоступен, приложение продолжает работать — кэш используется
как оптимизация, а не как критичная зависимость.
"""

import logging
import os

import redis

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def get_cache() -> redis.Redis:
    """Возвращает singleton клиента Redis."""
    global _client
    if _client is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            _client = redis.from_url(url, decode_responses=True, socket_timeout=1)
            _client.ping()  # проверка, что соединение реально работает
        except redis.RedisError as e:
            logger.warning("Redis недоступен (%s): %s. Работаем без кэша.", url, e)
            _client = None
    return _client  # type: ignore[return-value]
