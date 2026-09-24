"""Тесты публичного API: детали проекта и список транзакций."""

from datetime import UTC, datetime

from app import db as _db
from app.models import ExpenseCategory, IncomeCategory, Project, Transaction


def _seed(app):
    """2 проекта, 5 транзакций: доходы/расходы, RUB/USD, разные даты."""
    with app.app_context():
        p1 = Project(name="Альфа")
        p2 = Project(name="Бета")
        inc = IncomeCategory(name="Доход")
        exp = ExpenseCategory(name="Расход")
        _db.session.add_all([p1, p2, inc, exp])
        _db.session.commit()

        _db.session.add_all(
            [
                Transaction(
                    project_id=p1.id,
                    type="income",
                    category_id=inc.id,
                    amount=1000,
                    currency="RUB",
                    date=datetime(2026, 9, 1, tzinfo=UTC),
                ),
                Transaction(
                    project_id=p1.id,
                    type="income",
                    category_id=inc.id,
                    amount=100,
                    currency="USD",
                    date=datetime(2026, 9, 15, tzinfo=UTC),
                ),
                Transaction(
                    project_id=p1.id,
                    type="expense",
                    category_id=exp.id,
                    amount=200,
                    currency="RUB",
                    date=datetime(2026, 9, 20, tzinfo=UTC),
                ),
                Transaction(
                    project_id=p2.id,
                    type="income",
                    category_id=inc.id,
                    amount=3000,
                    currency="RUB",
                    date=datetime(2026, 10, 1, tzinfo=UTC),
                ),
                Transaction(
                    project_id=p2.id,
                    type="expense",
                    category_id=exp.id,
                    amount=500,
                    currency="RUB",
                    date=datetime(2026, 10, 5, tzinfo=UTC),
                ),
            ]
        )
        _db.session.commit()
        return p1.id, p2.id


# ============================================================
#   /projects/<id>
# ============================================================


def test_project_detail_returns_data(client, app):
    p1_id, _ = _seed(app)

    response = client.get(f"/api/v1/projects/{p1_id}")

    assert response.status_code == 200
    data = response.get_json()
    assert data["name"] == "Альфа"
    assert data["transactions_count"] == 3
    assert len(data["transactions"]) == 3
    # Самая свежая — первая
    assert data["transactions"][0]["type"] == "expense"


def test_project_detail_404(client):
    response = client.get("/api/v1/projects/99999")

    assert response.status_code == 404
    assert response.get_json()["error"] == "not_found"


def test_project_detail_ignores_deleted(client, app):
    with app.app_context():
        p = Project(name="Удалённый", is_deleted=True)
        _db.session.add(p)
        _db.session.commit()
        p_id = p.id

    response = client.get(f"/api/v1/projects/{p_id}")

    assert response.status_code == 404


# ============================================================
#   /transactions
# ============================================================


def test_transactions_empty(client):
    response = client.get("/api/v1/transactions")

    assert response.status_code == 200
    data = response.get_json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["pages"] == 0


def test_transactions_lists_all(client, app):
    _seed(app)

    response = client.get("/api/v1/transactions")

    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 5
    assert data["count"] == 5
    assert data["page"] == 1


def test_transactions_filter_by_type(client, app):
    _seed(app)

    response = client.get("/api/v1/transactions?type=expense")
    data = response.get_json()

    assert data["total"] == 2
    assert all(t["type"] == "expense" for t in data["items"])


def test_transactions_filter_by_currency(client, app):
    _seed(app)

    response = client.get("/api/v1/transactions?currency=USD")
    data = response.get_json()

    assert data["total"] == 1
    assert data["items"][0]["currency"] == "USD"


def test_transactions_filter_by_project(client, app):
    p1_id, p2_id = _seed(app)

    response = client.get(f"/api/v1/transactions?project_id={p1_id}")
    data = response.get_json()

    assert data["total"] == 3
    assert all(t["project_id"] == p1_id for t in data["items"])


def test_transactions_filter_by_date_range(client, app):
    _seed(app)

    response = client.get("/api/v1/transactions?date_from=2026-10-01&date_to=2026-10-31")
    data = response.get_json()

    assert data["total"] == 2


def test_transactions_pagination(client, app):
    _seed(app)

    response = client.get("/api/v1/transactions?per_page=2&page=1")
    data = response.get_json()

    assert data["count"] == 2
    assert data["total"] == 5
    assert data["pages"] == 3  # 5/2 → 3 страницы
    assert data["page"] == 1


def test_transactions_pagination_second_page(client, app):
    _seed(app)

    response = client.get("/api/v1/transactions?per_page=2&page=2")
    data = response.get_json()

    assert data["count"] == 2
    assert data["page"] == 2


def test_transactions_pagination_caps_per_page(client, app):
    """per_page > 200 → обрезается до 200."""
    _seed(app)

    response = client.get("/api/v1/transactions?per_page=1000")
    data = response.get_json()

    assert data["per_page"] == 200


def test_transactions_invalid_date_400(client):
    response = client.get("/api/v1/transactions?date_from=bad")

    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_parameter"


def test_transactions_invalid_page_400(client):
    response = client.get("/api/v1/transactions?page=abc")

    assert response.status_code == 400


def test_transactions_sorted_by_date_desc(client, app):
    _seed(app)

    response = client.get("/api/v1/transactions?per_page=10")
    data = response.get_json()

    dates = [t["date"] for t in data["items"]]
    assert dates == sorted(dates, reverse=True)


def test_transactions_excludes_deleted(client, app):
    _seed(app)
    with app.app_context():
        _db.session.add(
            Transaction(
                project_id=1,
                type="income",
                category_id=1,
                amount=999,
                currency="RUB",
                is_deleted=True,
                date=datetime(2026, 9, 1, tzinfo=UTC),
            )
        )
        _db.session.commit()

    response = client.get("/api/v1/transactions")
    data = response.get_json()

    # Удалённая не попала
    assert data["total"] == 5
    assert all(t["amount"] != 999 for t in data["items"])
