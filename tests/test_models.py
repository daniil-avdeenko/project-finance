from datetime import UTC, date, datetime

import pytest
from wtforms.validators import ValidationError

from app import db as _db
from app.forms import TransactionForm
from app.models import ExpenseCategory, IncomeCategory, Project, Transaction
from app.services.currency_service import upsert_rates


def test_create_project(app):
    """Проверяем, что проект создаётся напрямую в БД."""
    with app.app_context():
        project = Project(name="Тестовый проект", description="Описание")
        _db.session.add(project)
        _db.session.commit()

        assert project.id is not None
        assert Project.query.count() == 1


def test_create_transaction_directly(app):
    """Проверяем, что транзакция создаётся через модель."""
    with app.app_context():
        # Создаём проект и категорию
        project = Project(name="Проект")
        category = IncomeCategory(name="Доход")
        _db.session.add_all([project, category])
        _db.session.commit()

        # Создаём транзакцию
        transaction = Transaction(
            project_id=project.id,
            type="income",
            category_id=category.id,
            amount=50000,
            description="Тестовая транзакция",
        )
        _db.session.add(transaction)
        _db.session.commit()

        assert transaction.id is not None
        assert transaction.amount == 50000
        assert Transaction.query.count() == 1


def test_create_transaction_via_route(auth_client, app):
    """Проверяем создание транзакции через POST-запрос."""
    from datetime import UTC, datetime, timedelta

    with app.app_context():
        # Проект создан в прошлом, чтобы дата транзакции прошла валидацию
        project = Project(
            name="Проект",
            created_at=datetime.now(UTC) - timedelta(days=30),
        )
        category = IncomeCategory(name="Доход")
        _db.session.add_all([project, category])
        _db.session.commit()

        project_id = project.id
        category_id = category.id

    # Отправляем POST-запрос на создание транзакции
    response = auth_client.post(
        "/transactions/create",
        data={
            "type": "income",
            "project_id": project_id,
            "category_id": category_id,
            "amount": "50000",
            "currency": "RUB",
            "description": "Тестовая транзакция",
            "date": "2026-09-12",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        assert Transaction.query.count() == 1
        saved = Transaction.query.first()
        assert saved.amount == 50000
        assert saved.type == "income"


def test_project_profit_calculation(app):
    """Проверяем расчёт прибыли и рентабельности."""
    with app.app_context():
        project = Project(name="Проект")
        income_cat = IncomeCategory(name="Доход")
        expense_cat = ExpenseCategory(name="Расход")
        _db.session.add_all([project, income_cat, expense_cat])
        _db.session.commit()

        # Доход 100000
        _db.session.add(
            Transaction(
                project_id=project.id,
                type="income",
                category_id=income_cat.id,
                amount=100000,
            )
        )
        # Расход 40000
        _db.session.add(
            Transaction(
                project_id=project.id,
                type="expense",
                category_id=expense_cat.id,
                amount=40000,
            )
        )
        _db.session.commit()

        assert project.total_income == 100000
        assert project.total_expense == 40000
        assert project.profit == 60000
        assert project.profitability == 60.0


def test_profitability_zero_income(app):
    """Проект без доходов: рентабельность = 0, деления на ноль нет."""
    with app.app_context():
        project = Project(name="Без доходов")
        _db.session.add(project)
        _db.session.commit()

        assert project.total_income == 0
        assert project.profitability == 0


def test_amount_validation_empty(app):
    """Пустая сумма не проходит валидацию формы."""
    with app.app_context():
        form = TransactionForm()
        form.amount.data = ""
        with pytest.raises(ValidationError):
            form.validate_amount(form.amount)


def test_amount_validation_negative(app):
    """Отрицательная сумма не проходит валидацию."""
    with app.app_context():
        form = TransactionForm()
        form.amount.data = "-100"
        with pytest.raises(ValidationError):
            form.validate_amount(form.amount)


def test_amount_validation_with_spaces(app):
    """Сумма с пробелами и запятой корректно парсится в float."""
    with app.app_context():
        form = TransactionForm()
        form.amount.data = "1 234,56"
        form.validate_amount(form.amount)
        assert form.amount.data == 1234.56


class FakeRate:
    def __init__(self, code, nominal, rate, rate_date):
        self.code = code
        self.nominal = nominal
        self.rate = rate
        self.rate_date = rate_date


def test_transaction_amount_rub_for_rub(app):
    """Транзакция в рублях — amount_rub = amount."""
    with app.app_context():
        project = Project(name="P")
        cat = IncomeCategory(name="C")
        _db.session.add_all([project, cat])
        _db.session.commit()

        t = Transaction(
            project_id=project.id,
            type="income",
            category_id=cat.id,
            amount=5000,
            currency="RUB",
        )
        _db.session.add(t)
        _db.session.commit()

        assert t.amount_rub == 5000


def test_transaction_amount_rub_for_usd(app):
    """Транзакция в долларах — конвертация по курсу на дату."""
    with app.app_context():
        upsert_rates([FakeRate("USD", 1, 84.50, date(2026, 9, 19))])

        project = Project(name="P")
        cat = IncomeCategory(name="C")
        _db.session.add_all([project, cat])
        _db.session.commit()

        t = Transaction(
            project_id=project.id,
            type="income",
            category_id=cat.id,
            amount=100,
            currency="USD",
            date=datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
        )
        _db.session.add(t)
        _db.session.commit()

        assert t.amount_rub == 8450.0


def test_project_profit_mixed_currencies(app):
    """Проект с транзакциями в разных валютах — прибыль в рублях."""
    with app.app_context():
        upsert_rates([FakeRate("USD", 1, 84.50, date(2026, 9, 19))])

        project = Project(name="P")
        income_cat = IncomeCategory(name="Income")
        expense_cat = ExpenseCategory(name="Expense")
        _db.session.add_all([project, income_cat, expense_cat])
        _db.session.commit()

        tx_date = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

        # Доход: 100 USD = 8450 RUB
        _db.session.add(
            Transaction(
                project_id=project.id,
                type="income",
                category_id=income_cat.id,
                amount=100,
                currency="USD",
                date=tx_date,
            )
        )
        # Расход: 2000 RUB
        _db.session.add(
            Transaction(
                project_id=project.id,
                type="expense",
                category_id=expense_cat.id,
                amount=2000,
                currency="RUB",
                date=tx_date,
            )
        )
        _db.session.commit()

        assert project.total_income == 8450.0
        assert project.total_expense == 2000.0
        assert project.profit == 6450.0
        assert project.profitability == pytest.approx(76.33, abs=0.01)
