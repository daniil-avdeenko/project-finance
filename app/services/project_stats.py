"""
Сервис расчёта финансовых показателей проектов.

Загружает курсы один раз и считает все показатели в памяти.
Убирает N+1: вместо запроса курса на каждую транзакцию — один
get_rates_map на всю страницу или экспорт.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass

from app.services.currency_service import CachedRate, convert_with_rates


@dataclass(frozen=True)
class ProjectStats:
    """Готовые показатели проекта в рублях."""

    total_income: float
    total_expense: float
    profit: float
    profitability: float


# Заглушка для проектов без транзакций.
EMPTY_STATS = ProjectStats(total_income=0.0, total_expense=0.0, profit=0.0, profitability=0.0)


class ProjectStatsService:
    """Расчёт финансовых показателей проектов по транзакциям."""

    @staticmethod
    def calculate(
        transactions: list,
        rates_map: dict[str, list[CachedRate]],
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


def compute_stats_by_project(
    transactions: list,
    rates_map: dict[str, list[CachedRate]],
) -> dict[int, ProjectStats]:
    """
    Группирует транзакции по project_id и считает статистику для каждой группы.

    Один проход по транзакциям + один вызов calculate на проект.
    """
    by_project: dict[int, list] = defaultdict(list)
    for t in transactions:
        by_project[t.project_id].append(t)

    return {pid: ProjectStatsService.calculate(txs, rates_map) for pid, txs in by_project.items()}


def count_by_project(transactions: list) -> dict[int, int]:
    """
    Считает количество транзакций на проект одним проходом.
    """
    return dict(Counter(t.project_id for t in transactions))
