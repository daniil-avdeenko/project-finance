"""
Сервис категорий доходов/расходов с кэшированием в Redis.

Категории меняются редко (админ создаёт при инициализации), но читаются
на каждый API-запрос и на несколько HTML-страниц. Кэш снижает нагрузку
на PostgreSQL и ускоряет ответы API для Telegram-агента.

Инвалидация — при любом CRUD категорий (см. routes/categories.py).
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import timedelta

from app.cache import get_cache, mark_cache_unavailable
from app.models import ExpenseCategory, IncomeCategory

logger = logging.getLogger(__name__)

CATEGORIES_CACHE_KEY = "categories:all"
CATEGORIES_CACHE_TTL = timedelta(hours=1)


@dataclass(frozen=True)
class CategoryEntry:
    """Лёгкая копия категории для сериализации в JSON."""

    id: int
    name: str


def get_categories() -> dict[str, list[CategoryEntry]]:
    """
    Возвращает {"income": [...], "expense": [...]}.

    Кэшируется в Redis (TTL 1 час). При недоступном Redis — прямо из БД.
    Вызывается из wrappers ниже: get_categories_map / get_category_dicts.
    """
    cache = get_cache()

    if cache:
        try:
            cached = cache.get(CATEGORIES_CACHE_KEY)
            if cached:
                parsed = json.loads(cached)
                return {
                    type_: [CategoryEntry(id=c["id"], name=c["name"]) for c in items]
                    for type_, items in parsed.items()
                }
        except Exception as e:
            logger.warning("Redis read error (%s): %s", CATEGORIES_CACHE_KEY, e)
            mark_cache_unavailable()
            cache = None

    result = {
        "income": [CategoryEntry(id=c.id, name=c.name) for c in IncomeCategory.query.all()],
        "expense": [CategoryEntry(id=c.id, name=c.name) for c in ExpenseCategory.query.all()],
    }

    if cache:
        try:
            serialized = {type_: [asdict(c) for c in items] for type_, items in result.items()}
            cache.setex(CATEGORIES_CACHE_KEY, CATEGORIES_CACHE_TTL, json.dumps(serialized))
        except Exception as e:
            logger.warning("Redis write error (%s): %s", CATEGORIES_CACHE_KEY, e)
            mark_cache_unavailable()

    return result


def get_categories_map() -> dict[tuple[str, int], str]:
    """
    {(type, id): name} — для API-сериализаторов и _load_categories.
    """
    categories = get_categories()
    return {
        (type_, entry.id): entry.name for type_, entries in categories.items() for entry in entries
    }


def get_category_dicts() -> tuple[dict[int, str], dict[int, str]]:
    """(income_map, expense_map) — для HTML-шаблонов, где тип известен заранее."""
    categories = get_categories()
    return (
        {c.id: c.name for c in categories["income"]},
        {c.id: c.name for c in categories["expense"]},
    )


def invalidate_categories_cache() -> None:
    """
    Сбрасывает кэш категорий. Вызывается из CRUD-роутов после commit.
    """
    cache = get_cache()
    if cache is None:
        return
    try:
        cache.delete(CATEGORIES_CACHE_KEY)
        logger.info("Categories cache invalidated")
    except Exception as e:
        logger.warning("Cache invalidation error: %s", e)
        mark_cache_unavailable()
