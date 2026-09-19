"""
Сервис расчёта финансовых показателей проектов.

Загружает курсы один раз и считает все показатели в памяти.
Убирает N+1: вместо запроса курса на каждую транзакцию — один
get_rates_map на всю страницу.
"""

from dataclasses import dataclass

from app.models import CurrencyRate
from app.services.currency_service import convert_with_rates


@dataclass(frozen=True)
class ProjectStats:
    """Готовые показатели проекта в рублях."""

    total_income: float
    total_expense: float
    profit: float
    profitability: float


class ProjectStatsService:
    """Расчёт финансовых показателей проектов по транзакциям."""

    @staticmethod
    def calculate(
        transactions: list,
        rates_map: dict[str, list[CurrencyRate]],
    ) -> ProjectStats:
        """
        Считает income / expense / profit / profitability в рублях.

        transactions — список Transaction (уже отфильтрованный по датам
        и проекту, если нужно).
        rates_map — предзагруженный get_rates_map.
        """
        total_income = 0.0
        total_expense = 0.0

        for t in transactions:
            on_date = t.date.date() if t.date else None
            rub = convert_with_rates(
                t.amount,
                t.currency or "RUB",
                on_date,
                rates_map,
            )
            if t.type == "income":
                total_income += rub
            elif t.type == "expense":
                total_expense += rub

        total_income = round(total_income, 2)
        total_expense = round(total_expense, 2)
        profit = round(total_income - total_expense, 2)
        profitability = round(profit / total_income * 100, 2) if total_income > 0 else 0.0

        return ProjectStats(
            total_income=total_income,
            total_expense=total_expense,
            profit=profit,
            profitability=profitability,
        )

    @staticmethod
    def collect_codes(transactions: list) -> set[str]:
        """Возвращает множество валют, встречающихся в транзакциях."""
        return {t.currency for t in transactions if t.currency}
