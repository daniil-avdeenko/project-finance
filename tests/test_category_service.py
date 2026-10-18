"""Тесты кэширования категорий."""

import fakeredis
import pytest

from app.services import category_service
from app.services.category_service import (
    get_categories,
    get_categories_map,
    get_category_dicts,
    invalidate_categories_cache,
)


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    """Подменяет Redis на fakeredis для всех тестов в файле."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(category_service, "get_cache", lambda: fake)
    return fake


def test_get_categories_caches_result(app, mock_redis):
    """Первый вызов идёт в БД, второй — из кэша."""
    from app import db
    from app.models import ExpenseCategory, IncomeCategory

    with app.app_context():
        db.session.add_all(
            [
                IncomeCategory(name="Consulting"),
                ExpenseCategory(name="Taxes"),
            ]
        )
        db.session.commit()

        result1 = get_categories()
        assert len(result1["income"]) == 1
        assert len(result1["expense"]) == 1
        assert result1["income"][0].name == "Consulting"
        assert mock_redis.exists("categories:all") == 1

        result2 = get_categories()
        assert result2["income"][0].name == "Consulting"


def test_get_categories_map_shape(app, mock_redis):
    """Возвращает {(type, id): name} — для API."""
    from app import db
    from app.models import IncomeCategory

    with app.app_context():
        cat = IncomeCategory(name="Consulting")
        db.session.add(cat)
        db.session.commit()

        result = get_categories_map()
        assert ("income", cat.id) in result
        assert result[("income", cat.id)] == "Consulting"


def test_get_category_dicts_shape(app, mock_redis):
    """Возвращает (income_map, expense_map) — для HTML."""
    from app import db
    from app.models import ExpenseCategory

    with app.app_context():
        cat = ExpenseCategory(name="Taxes")
        db.session.add(cat)
        db.session.commit()

        income, expense = get_category_dicts()
        assert cat.id in expense
        assert expense[cat.id] == "Taxes"
        assert income == {}


def test_invalidate_categories_cache(app, mock_redis):
    """После invalidate кэш пуст."""
    from app import db
    from app.models import IncomeCategory

    with app.app_context():
        db.session.add(IncomeCategory(name="A"))
        db.session.commit()
        get_categories()
        assert mock_redis.exists("categories:all") == 1

        invalidate_categories_cache()
        assert mock_redis.exists("categories:all") == 0


def test_get_categories_works_without_redis(app, monkeypatch):
    """Без Redis работает напрямую с БД."""
    from app import db
    from app.models import IncomeCategory

    monkeypatch.setattr(category_service, "get_cache", lambda: None)

    with app.app_context():
        db.session.add(IncomeCategory(name="A"))
        db.session.commit()

        result = get_categories()
        assert len(result["income"]) == 1
        assert result["income"][0].name == "A"
