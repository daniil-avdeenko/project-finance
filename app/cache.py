"""
Клиент Redis для кэширования.

Ленивая инициализация: соединение устанавливается при первом обращении.
Если Redis недоступен, приложение продолжает работать без кэша.
"""

import logging
import os

import redis

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None
_client_unavailable: bool = False


def get_cache() -> redis.Redis | None:
    """
    Возвращает singleton клиента Redis или None, если Redis недоступен.

    Первый вызов пробует подключиться. При неудаче запоминает это в
    _client_unavailable и следующие вызовы возвращают None сразу,
    без ожидания на TCP-connect.
    """
    global _client, _client_unavailable

    if _client_unavailable:
        return None
    if _client is not None:
        return _client

    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        client = redis.from_url(
            url,
            decode_responses=True,
            socket_timeout=1,
            socket_connect_timeout=1,
        )
        client.ping()
        _client = client
    except redis.RedisError as e:
        logger.warning("Redis недоступен (%s): %s. Работаем без кэша.", url, e)
        _client_unavailable = True

    return _client
