import calendar
import csv
from calendar import monthrange
from datetime import UTC, datetime
from io import StringIO

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.decorators import admin_required
from app.forms import ProjectForm
from app.helpers import make_csv_response, parse_ids_from_string
from app.models import Employee, ExpenseCategory, IncomeCategory, Project, Transaction
from app.routes.blueprint import main_bp


@main_bp.route("/")
@login_required
def index():
    """
    Дашборд: статистика по проектам за выбранный период (месяц или всё время).
    """
    now = datetime.now(UTC)
    current_year = now.year

    month_param = request.args.get("month")
    year_param = request.args.get("year")

    # Определяем период
    if month_param == "all" or month_param is None:
        start_date = None
        end_date = None
        period_label = "Весь период"
        selected_month = None
        selected_year = None
    else:
        selected_month = int(month_param)
        selected_year = int(year_param) if year_param else current_year

        if selected_year != current_year:
            start_date = None
            end_date = None
            period_label = "Весь период"
            selected_month = None
            selected_year = None
        else:
            if selected_month < 1 or selected_month > 12:
                selected_month = 1
            start_date = datetime(selected_year, selected_month, 1, tzinfo=UTC)
            last_day = monthrange(selected_year, selected_month)[1]
            end_date = datetime(selected_year, selected_month, last_day, 23, 59, 59, tzinfo=UTC)
            period_label = f"{calendar.month_name[selected_month]} {selected_year}"

    # Базовые запросы с фильтром по дате
    income_query = Transaction.query.filter(Transaction.type == "income")
    expense_query = Transaction.query.filter(Transaction.type == "expense")
    if start_date:
        income_query = income_query.filter(Transaction.date >= start_date)
        expense_query = expense_query.filter(Transaction.date >= start_date)
    if end_date:
        income_query = income_query.filter(Transaction.date <= end_date)
        expense_query = expense_query.filter(Transaction.date <= end_date)

    incomes = income_query.all()
    expenses = expense_query.all()
    total_income = sum(t.amount_rub for t in incomes)
    total_expense = sum(t.amount_rub for t in expenses)
    total_profit = total_income - total_expense
    overall_profitability = 0
    if total_income > 0:
        overall_profitability = round((total_profit / total_income) * 100, 2)

    # Статистика по проектам
    all_projects = Project.query.all()
    projects_stats = []
    for project in all_projects:
        p_income_query = project.transactions.filter(Transaction.type == "income")
        p_expense_query = project.transactions.filter(Transaction.type == "expense")
        if start_date:
            p_income_query = p_income_query.filter(Transaction.date >= start_date)
            p_expense_query = p_expense_query.filter(Transaction.date >= start_date)
        if end_date:
            p_income_query = p_income_query.filter(Transaction.date <= end_date)
            p_expense_query = p_expense_query.filter(Transaction.date <= end_date)

        p_income = sum(t.amount_rub for t in p_income_query.all())
        p_expense = sum(t.amount_rub for t in p_expense_query.all())
        p_profit = p_income - p_expense
        p_profitability = 0
        if p_income > 0:
            p_profitability = round((p_profit / p_income) * 100, 2)
        projects_stats.append(
            {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "profit": p_profit,
                "profitability": p_profitability,
                "income": p_income,
                "expense": p_expense,
            }
        )

    total_projects = len(all_projects)

    # Список месяцев текущего года (от текущего к январю)
    current_month = now.month
    months = []
    for m in range(current_month, 0, -1):
        months.append(
            {
                "month": m,
                "year": current_year,
                "label": f"{calendar.month_name[m]} {current_year}",
            }
        )

    return render_template(
        "index.html",
        projects_stats=projects_stats,
        total_projects=total_projects,
        total_income=total_income,
        total_expense=total_expense,
        total_profit=total_profit,
        overall_profitability=overall_profitability,
        selected_month=selected_month,
        selected_year=selected_year,
        months=months,
        period_label=period_label,
    )


@main_bp.route("/projects")
@login_required
def projects_list():
    """Список всех проектов."""
    projects = Project.query.all()
    return render_template("projects/list.html", projects=projects)


@main_bp.route("/projects/create", methods=["GET", "POST"])
@login_required
@admin_required
def project_create():
    """Создание нового проекта (только для админов)."""
    form = ProjectForm()
    if form.validate_on_submit():
        project = Project(name=form.name.data, description=form.description.data)
        try:
            db.session.add(project)
            db.session.commit()
            flash("Проект успешно создан!", "success")
            return redirect(url_for("main.projects_list"))
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при создании проекта: {str(e)}", "danger")
    return render_template("projects/create.html", form=form)


@main_bp.route("/projects/<int:project_id>", methods=["GET", "POST"])
@login_required
def project_detail(project_id):
    """
    Детальная страница проекта.
    Если запрос POST и пользователь админ – обновляет список сотрудников.
    """
    project = Project.query.get_or_404(project_id)

    if request.method == "POST" and current_user.is_admin():
        employee_ids = parse_ids_from_string(request.form.get("employee_ids", ""))
        employees = Employee.query.filter(Employee.id.in_(employee_ids)).all()
        project.employees = employees
        try:
            db.session.commit()
            flash("Список сотрудников обновлён", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при сохранении: {str(e)}", "danger")
        return redirect(url_for("main.project_detail", project_id=project.id))

    transactions = project.transactions.order_by(Transaction.date.desc()).all()
    income_categories = {c.id: c.name for c in IncomeCategory.query.all()}
    expense_categories = {c.id: c.name for c in ExpenseCategory.query.all()}
    all_employees = Employee.query.all()

    return render_template(
        "projects/detail.html",
        project=project,
        transactions=transactions,
        income_categories=income_categories,
        expense_categories=expense_categories,
        all_employees=all_employees,
    )


@main_bp.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def project_edit(project_id):
    """Редактирование проекта (только для админов)."""
    project = Project.query.get_or_404(project_id)
    form = ProjectForm(obj=project)
    if form.validate_on_submit():
        project.name = form.name.data
        project.description = form.description.data
        try:
            db.session.commit()
            flash("Проект обновлён", "success")
            return redirect(url_for("main.project_detail", project_id=project.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при обновлении: {str(e)}", "danger")
    return render_template("projects/edit.html", form=form, project=project)


@main_bp.route("/projects/<int:project_id>/delete", methods=["POST"])
@login_required
@admin_required
def project_delete(project_id):
    """Удаление проекта (только для админов)."""
    project = Project.query.get_or_404(project_id)
    try:
        db.session.delete(project)
        db.session.commit()
        flash("Проект удалён", "warning")
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка при удалении: {str(e)}", "danger")
    return redirect(url_for("main.projects_list"))


@main_bp.route("/projects/export")
@login_required
def export_projects_csv():
    projects = Project.query.all()
    si = StringIO()
    writer = csv.writer(si, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(
        [
            "ID",
            "Название",
            "Описание",
            "Доходы (₽)",
            "Расходы (₽)",
            "Прибыль (₽)",
            "Рентабельность (%)",
            "Кол-во сотрудников",
            "Кол-во транзакций",
        ]
    )
    for p in projects:
        writer.writerow(
            [
                p.id,
                p.name,
                p.description or "",
                round(p.total_income, 2),
                round(p.total_expense, 2),
                round(p.profit, 2),
                p.profitability,
                len(p.employees),
                p.transactions.count(),
            ]
        )
    csv_content = si.getvalue()
    si.close()
    return make_csv_response(csv_content, "projects_export.csv")


@main_bp.route("/chart")
@login_required
def chart():
    """
    Страница графика рентабельности по проектам за последние 6 месяцев.
    """
    now = datetime.now(UTC)
    projects = Project.query.all()

    month_labels = []
    month_ranges = []
    for i in range(1, 7):
        month = now.month - i
        year = now.year
        if month <= 0:
            month += 12
            year -= 1
        start_date = datetime(year, month, 1, tzinfo=UTC)
        last_day = monthrange(year, month)[1]
        end_date = datetime(year, month, last_day, 23, 59, 59, tzinfo=UTC)
        label = f"{calendar.month_name[month]} {year}"
        month_labels.append(label)
        month_ranges.append((start_date, end_date))

    month_labels.reverse()
    month_ranges.reverse()

    color_palette = [
        "#FF6384",
        "#36A2EB",
        "#FFCE56",
        "#4BC0C0",
        "#9966FF",
        "#FF9F40",
        "#C9CBCF",
        "#536DFF",
        "#FF6384",
        "#36A2EB",
    ]

    projects_data = []
    for idx, project in enumerate(projects):
        data = []
        for start_date, end_date in month_ranges:
            incomes = project.transactions.filter(
                Transaction.type == "income",
                Transaction.date >= start_date,
                Transaction.date <= end_date,
            ).all()
            expenses = project.transactions.filter(
                Transaction.type == "expense",
                Transaction.date >= start_date,
                Transaction.date <= end_date,
            ).all()
            total_income = sum(t.amount_rub for t in incomes)
            total_expense = sum(t.amount_rub for t in expenses)
            profit = total_income - total_expense
            profitability = 0
            if total_income > 0:
                profitability = round((profit / total_income) * 100, 2)
            data.append(profitability)

        projects_data.append(
            {
                "id": project.id,
                "name": project.name,
                "data": data,
                "color": color_palette[idx % len(color_palette)],
            }
        )

    return render_template("chart.html", month_labels=month_labels, projects_data=projects_data)
