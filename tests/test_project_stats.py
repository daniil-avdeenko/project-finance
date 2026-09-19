"""Тесты ProjectStatsService и batch-загрузки курсов."""

from datetime import UTC, date, datetime

import pytest

from app import db as _db
from app.models import CurrencyRate, ExpenseCategory, IncomeCategory, Project, Transaction
from app.services.currency_service import get_rates_map
from app.services.project_stats import ProjectStatsService


class FakeRate:
    def __init__(self, code, nominal, rate, rate_date):
        self.code = code
        self.nominal = nominal
        self.rate = rate
        self.rate_date = rate_date


def _seed_rates(app):
    with app.app_context():
        _db.session.add_all(
            [
                CurrencyRate(code="USD", rate_date=date(2026, 9, 18), nominal=1, rate_rub=84.0),
                CurrencyRate(code="USD", rate_date=date(2026, 9, 19), nominal=1, rate_rub=85.0),
                CurrencyRate(code="EUR", rate_date=date(2026, 9, 19), nominal=1, rate_rub=97.0),
            ]
        )
        _db.session.commit()


# ============================================================
#   get_rates_map
# ============================================================


def test_get_rates_map_returns_dict_of_lists(app):
    _seed_rates(app)

    with app.app_context():
        rates = get_rates_map({"USD", "EUR"})

        assert set(rates.keys()) == {"USD", "EUR"}
        # USD отсортирован по дате desc
        assert rates["USD"][0].rate_date == date(2026, 9, 19)
        assert rates["USD"][1].rate_date == date(2026, 9, 18)


def test_get_rates_map_skips_rub(app):
    with app.app_context():
        assert get_rates_map({"RUB", "USD"}) == {} or set(get_rates_map({"RUB"}).keys()) == set()


def test_get_rates_map_empty_input(app):
    with app.app_context():
        assert get_rates_map(set()) == {}


# ============================================================
#   ProjectStatsService.calculate
# ============================================================


def test_calculate_empty_transactions(app):
    with app.app_context():
        stats = ProjectStatsService.calculate([], {})

        assert stats.total_income == 0
        assert stats.total_expense == 0
        assert stats.profit == 0
        assert stats.profitability == 0


def test_calculate_mixed_currencies(app):
    """Транзакции в RUB/USD/EUR — считаются в рублях."""
    _seed_rates(app)

    with app.app_context():
        rates_map = get_rates_map({"USD", "EUR"})

        project = Project(name="P")
        inc = IncomeCategory(name="I")
        exp = ExpenseCategory(name="E")
        _db.session.add_all([project, inc, exp])
        _db.session.commit()

        tx_date = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
        transactions = [
            # Доход 100 USD * 85 = 8500
            Transaction(
                project_id=project.id,
                type="income",
                category_id=inc.id,
                amount=100,
                currency="USD",
                date=tx_date,
            ),
            # Доход 100 EUR * 97 = 9700
            Transaction(
                project_id=project.id,
                type="income",
                category_id=inc.id,
                amount=100,
                currency="EUR",
                date=tx_date,
            ),
            # Расход 5000 RUB
            Transaction(
                project_id=project.id,
                type="expense",
                category_id=exp.id,
                amount=5000,
                currency="RUB",
                date=tx_date,
            ),
        ]
        _db.session.add_all(transactions)
        _db.session.commit()

        stats = ProjectStatsService.calculate(transactions, rates_map)

        assert stats.total_income == 18200.0
        assert stats.total_expense == 5000.0
        assert stats.profit == 13200.0
        assert stats.profitability == pytest.approx(72.53, abs=0.01)


def test_calculate_profitability_zero_income(app):
    with app.app_context():
        project = Project(name="P")
        exp = ExpenseCategory(name="E")
        _db.session.add_all([project, exp])
        _db.session.commit()

        t = Transaction(
            project_id=project.id,
            type="expense",
            category_id=exp.id,
            amount=100,
            currency="RUB",
        )
        _db.session.add(t)
        _db.session.commit()

        stats = ProjectStatsService.calculate([t], {})

        assert stats.profitability == 0


def test_collect_codes(app):
    with app.app_context():
        project = Project(name="P")
        inc = IncomeCategory(name="I")
        _db.session.add_all([project, inc])
        _db.session.commit()

        transactions = [
            Transaction(
                project_id=project.id, type="income", category_id=inc.id, amount=1, currency="USD"
            ),
            Transaction(
                project_id=project.id, type="income", category_id=inc.id, amount=1, currency="EUR"
            ),
            Transaction(
                project_id=project.id, type="income", category_id=inc.id, amount=1, currency="RUB"
            ),
        ]

        assert ProjectStatsService.collect_codes(transactions) == {"USD", "EUR", "RUB"}
