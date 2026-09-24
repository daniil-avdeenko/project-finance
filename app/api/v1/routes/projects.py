"""
Эндпоинты публичного API: сводка и список проектов.

Финансовые показатели считаются через ProjectStatsService — тот же
сервис, что на HTML-дашборде. Гарантирует консистентность
цифр между сайтом и API.
"""

from collections import defaultdict

from flask import jsonify, request
from sqlalchemy.orm import joinedload

from app.api.v1 import api_v1_bp
from app.api.v1.serializers import (
    parse_date_param,
    project_detail_to_dict,
    project_to_dict,
    summary_to_dict,
    transaction_to_dict,
)
from app.models import (
    EmployeeProject,  # noqa: F401
    ExpenseCategory,
    IncomeCategory,
    Project,
    Transaction,
)
from app.services.currency_service import get_rates_map
from app.services.project_stats import ProjectStatsService


def _load_transactions(date_from, date_to) -> list:
    """Загружает активные транзакции за период + только по активным проектам."""
    active_project_ids = {p.id for p in Project.active().all()}

    query = Transaction.active()
    if date_from:
        query = query.filter(Transaction.date >= date_from)
    if date_to:
        query = query.filter(Transaction.date <= date_to)

    transactions = query.all()
    # Defense-in-depth: не показываем транзакции удалённых проектов
    return [t for t in transactions if t.project_id in active_project_ids]


@api_v1_bp.route("/summary", methods=["GET"])
def api_summary():
    """
    Сводка по всем проектам за период.

    Query-параметры:
    - date_from: YYYY-MM-DD (опционально)
    - date_to:   YYYY-MM-DD (опционально)
    Без параметров — за всё время.
    """
    try:
        date_from = parse_date_param(request.args.get("date_from"), "date_from")
        date_to = parse_date_param(request.args.get("date_to"), "date_to")
    except ValueError as e:
        return jsonify({"error": "invalid_parameter", "message": str(e)}), 400

    transactions = _load_transactions(date_from, date_to)

    codes = ProjectStatsService.collect_codes(transactions)
    rates_map = get_rates_map(codes)
    stats = ProjectStatsService.calculate(transactions, rates_map)

    period = {
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
    }

    return jsonify(
        summary_to_dict(
            stats=stats,
            total_projects=Project.active().count(),
            period=period,
        )
    )


@api_v1_bp.route("/projects", methods=["GET"])
def api_projects_list():
    """
    Список активных проектов с финансовыми показателями.

    Query-параметры:
    - date_from: YYYY-MM-DD (опционально)
    - date_to:   YYYY-MM-DD (опционально)
    - sort:      name_asc | name_desc | profit_desc | profit_asc
                 (по умолчанию name_asc)
    """
    try:
        date_from = parse_date_param(request.args.get("date_from"), "date_from")
        date_to = parse_date_param(request.args.get("date_to"), "date_to")
    except ValueError as e:
        return jsonify({"error": "invalid_parameter", "message": str(e)}), 400

    transactions = _load_transactions(date_from, date_to)

    codes = ProjectStatsService.collect_codes(transactions)
    rates_map = get_rates_map(codes)

    tx_by_project: dict[int, list] = defaultdict(list)
    for t in transactions:
        tx_by_project[t.project_id].append(t)

    projects = Project.active().all()
    items = []
    for project in projects:
        stats = ProjectStatsService.calculate(tx_by_project[project.id], rates_map)
        items.append(project_to_dict(project, stats))

    # Сортировка
    sort = request.args.get("sort", "name_asc")
    sort_keys = {
        "name_asc": (lambda x: x["name"], False),
        "name_desc": (lambda x: x["name"], True),
        "profit_asc": (lambda x: x["profit"], False),
        "profit_desc": (lambda x: x["profit"], True),
    }
    if sort in sort_keys:
        key_func, reverse = sort_keys[sort]
        items.sort(key=key_func, reverse=reverse)

    return jsonify({"items": items, "count": len(items)})


@api_v1_bp.route("/projects/<int:project_id>", methods=["GET"])
def api_project_detail(project_id: int):
    """
    Детали проекта: финансы, сотрудники, транзакции.

    Удалённые проекты недоступны — 404.
    """
    project = Project.active().filter_by(id=project_id).first()
    if not project:
        return jsonify({"error": "not_found", "message": "Project not found"}), 404

    transactions = (
        Transaction.active()
        .options(joinedload(Transaction.project))
        .filter_by(project_id=project.id)
        .order_by(Transaction.date.desc())
        .all()
    )

    income_cats = {c.id: c.name for c in IncomeCategory.query.all()}
    expense_cats = {c.id: c.name for c in ExpenseCategory.query.all()}
    categories = {**income_cats, **expense_cats}

    codes = ProjectStatsService.collect_codes(transactions)
    rates_map = get_rates_map(codes)
    stats = ProjectStatsService.calculate(transactions, rates_map)

    return jsonify(project_detail_to_dict(project, stats, transactions, categories))


@api_v1_bp.route("/transactions", methods=["GET"])
def api_transactions_list():
    """
    Список транзакций с фильтрами и пагинацией.

    Query-параметры:
    - date_from: YYYY-MM-DD
    - date_to:   YYYY-MM-DD
    - type:      income | expense
    - currency:  RUB | USD | EUR
    - project_id: int
    - page:      int, по умолчанию 1
    - per_page:  int, по умолчанию 50, максимум 200
    """
    try:
        date_from = parse_date_param(request.args.get("date_from"), "date_from")
        date_to = parse_date_param(request.args.get("date_to"), "date_to")
    except ValueError as e:
        return jsonify({"error": "invalid_parameter", "message": str(e)}), 400

    # Пагинация
    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", 50)), 1), 200)
    except ValueError:
        return jsonify(
            {"error": "invalid_parameter", "message": "page и per_page должны быть целыми"}
        ), 400

    # Фильтры
    query = Transaction.active()

    if date_from:
        query = query.filter(Transaction.date >= date_from)
    if date_to:
        query = query.filter(Transaction.date <= date_to)

    type_filter = request.args.get("type")
    if type_filter in ("income", "expense"):
        query = query.filter(Transaction.type == type_filter)

    currency_filter = request.args.get("currency")
    if currency_filter in ("RUB", "USD", "EUR"):
        query = query.filter(Transaction.currency == currency_filter)

    project_id = request.args.get("project_id", type=int)
    if project_id:
        query = query.filter(Transaction.project_id == project_id)

    total = query.count()
    transactions = (
        query.options(joinedload(Transaction.project))
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    income_cats = {c.id: c.name for c in IncomeCategory.query.all()}
    expense_cats = {c.id: c.name for c in ExpenseCategory.query.all()}
    categories = {**income_cats, **expense_cats}

    items = [transaction_to_dict(t, categories.get(t.category_id, "")) for t in transactions]

    return jsonify(
        {
            "items": items,
            "count": len(items),
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page if total else 0,
        }
    )
