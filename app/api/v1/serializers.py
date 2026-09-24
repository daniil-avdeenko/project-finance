"""
Сериализаторы для публичного API.

Превращают SQLAlchemy-модели в JSON-совместимые dict.
Отделены от роутов, чтобы переиспользовать в нескольких эндпоинтах.
"""

from datetime import datetime


def project_to_dict(project, stats) -> dict:
    """
    Проект + финансовые показатели в рублях.

    stats — ProjectStats из ProjectStatsService.
    """
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description or "",
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "income": stats.total_income,
        "expense": stats.total_expense,
        "profit": stats.profit,
        "profitability": stats.profitability,
    }


def summary_to_dict(stats, total_projects: int, period: dict) -> dict:
    """
    Сводка по всем проектам за период.

    stats — ProjectStats из ProjectStatsService (по всем транзакциям).
    period — {"date_from": ISO или None, "date_to": ISO или None}.
    """
    return {
        "period": period,
        "total_projects": total_projects,
        "total_income": stats.total_income,
        "total_expense": stats.total_expense,
        "total_profit": stats.profit,
        "overall_profitability": stats.profitability,
    }


def parse_date_param(value: str | None, field_name: str) -> datetime | None:
    """
    Парсит ISO-дату из query-параметра.

    Возвращает None, если значение не задано.
    Поднимает ValueError с понятным сообщением при некорректном формате.
    """
    if not value:
        return None
    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as err:
        raise ValueError(f"Параметр '{field_name}' должен быть в формате YYYY-MM-DD") from err
    from datetime import UTC

    return dt.replace(tzinfo=UTC)
