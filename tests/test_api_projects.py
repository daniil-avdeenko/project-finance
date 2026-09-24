"""Тесты публичного API: summary и projects."""

from datetime import UTC, datetime

from app import db as _db
from app.models import IncomeCategory, Project, Transaction


def _seed_two_projects(app):
    """Создаёт 2 проекта с транзакциями для тестов."""
    with app.app_context():
        p1 = Project(name="Альфа", description="Первый")
        p2 = Project(name="Бета", description="Второй")
        cat = IncomeCategory(name="Доход")
        _db.session.add_all([p1, p2, cat])
        _db.session.commit()

        # Альфа: доход 1000 + 500, расход 200 → прибыль 1300
        _db.session.add_all(
            [
                Transaction(
                    project_id=p1.id,
                    type="income",
                    category_id=cat.id,
                    amount=1000,
                    currency="RUB",
                    date=datetime(2026, 9, 15, tzinfo=UTC),
                ),
                Transaction(
                    project_id=p1.id,
                    type="income",
                    category_id=cat.id,
                    amount=500,
                    currency="RUB",
                    date=datetime(2026, 9, 20, tzinfo=UTC),
                ),
                Transaction(
                    project_id=p1.id,
                    type="expense",
                    category_id=cat.id,
                    amount=200,
                    currency="RUB",
                    date=datetime(2026, 9, 20, tzinfo=UTC),
                ),
            ]
        )
        # Бета: доход 300 → прибыль 300
        _db.session.add(
            Transaction(
                project_id=p2.id,
                type="income",
                category_id=cat.id,
                amount=300,
                currency="RUB",
                date=datetime(2026, 9, 10, tzinfo=UTC),
            )
        )
        _db.session.commit()
        return p1.id, p2.id


# ============================================================
#   /api/v1/summary
# ============================================================


def test_summary_empty(client):
    """Пустая БД — summary с нулями."""
    response = client.get("/api/v1/summary")

    assert response.status_code == 200
    data = response.get_json()
    assert data["total_projects"] == 0
    assert data["total_income"] == 0
    assert data["total_profit"] == 0


def test_summary_with_data(client, app):
    """Считает общие цифры по всем активным проектам."""
    _seed_two_projects(app)

    response = client.get("/api/v1/summary")

    assert response.status_code == 200
    data = response.get_json()
    assert data["total_projects"] == 2
    assert data["total_income"] == 1800.0  # 1000+500+300
    assert data["total_expense"] == 200.0
    assert data["total_profit"] == 1600.0
    assert data["period"] == {"date_from": None, "date_to": None}


def test_summary_filters_by_date(client, app):
    """Параметр date_from ограничивает выборку."""
    _seed_two_projects(app)

    response = client.get("/api/v1/summary?date_from=2026-09-18")

    assert response.status_code == 200
    data = response.get_json()
    # Осталось: 500 (альфа 20.09) + 200 расход + 300 (бета 10.09) — нет, 10.09 < 18
    # Осталось: 500 + 200 (расход отрицательный) → income 500, expense 200
    assert data["total_income"] == 500.0
    assert data["total_expense"] == 200.0


def test_summary_invalid_date_returns_400(client):
    """Некорректный формат даты → 400 с понятным сообщением."""
    response = client.get("/api/v1/summary?date_from=15-09-2026")

    assert response.status_code == 400
    data = response.get_json()
    assert data["error"] == "invalid_parameter"
    assert "date_from" in data["message"]


# ============================================================
#   /api/v1/projects
# ============================================================


def test_projects_empty(client):
    response = client.get("/api/v1/projects")

    assert response.status_code == 200
    data = response.get_json()
    assert data["items"] == []
    assert data["count"] == 0


def test_projects_with_data(client, app):
    _seed_two_projects(app)

    response = client.get("/api/v1/projects")

    assert response.status_code == 200
    data = response.get_json()
    assert data["count"] == 2
    names = [p["name"] for p in data["items"]]
    assert "Альфа" in names
    assert "Бета" in names

    alfa = next(p for p in data["items"] if p["name"] == "Альфа")
    assert alfa["income"] == 1500.0
    assert alfa["expense"] == 200.0
    assert alfa["profit"] == 1300.0
    assert alfa["profitability"] == round(1300 / 1500 * 100, 2)


def test_projects_sorted_by_profit_desc(client, app):
    _seed_two_projects(app)

    response = client.get("/api/v1/projects?sort=profit_desc")

    data = response.get_json()
    # Альфа (1300) > Бета (300)
    assert data["items"][0]["name"] == "Альфа"
    assert data["items"][1]["name"] == "Бета"


def test_projects_sorted_by_name_desc(client, app):
    _seed_two_projects(app)

    response = client.get("/api/v1/projects?sort=name_desc")

    data = response.get_json()
    # "Бета" > "Альфа" по строке
    assert data["items"][0]["name"] == "Бета"


def test_projects_ignores_deleted(client, app):
    """Удалённые проекты не попадают в список."""
    with app.app_context():
        p = Project(name="Удалённый", is_deleted=True)
        _db.session.add(p)
        _db.session.commit()

    response = client.get("/api/v1/projects")

    data = response.get_json()
    assert data["count"] == 0
