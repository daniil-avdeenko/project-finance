import csv
from datetime import UTC, datetime, timedelta
from io import StringIO

from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.decorators import admin_required
from app.forms import TransactionForm
from app.helpers import get_next_url, make_csv_response, safe_redirect
from app.models import ExpenseCategory, IncomeCategory, Project, Transaction
from app.routes.blueprint import main_bp


def set_category_choices(form, type_filter):
    """Заполняет choices для поля category_id в зависимости от типа транзакции."""
    if type_filter == "income":
        form.category_id.choices = [(c.id, c.name) for c in IncomeCategory.query.all()]
    elif type_filter == "expense":
        form.category_id.choices = [(c.id, c.name) for c in ExpenseCategory.query.all()]
    else:
        form.category_id.choices = []


def _validate_transaction_date(form, project) -> str | None:
    """
    Проверяет дату и время транзакции.

    Возвращает текст ошибки или None, если всё ок.
    """
    if not form.date.data:
        return None

    tx_dt = form.date.data
    if tx_dt.tzinfo is None:
        tx_dt = tx_dt.replace(tzinfo=UTC)

    project_start = project.created_at
    if project_start and project_start.tzinfo is None:
        project_start = project_start.replace(tzinfo=UTC)

    if project_start and tx_dt < project_start:
        return (
            f"Дата и время не могут быть раньше создания проекта "
            f"({project_start.strftime('%Y-%m-%d %H:%M')})"
        )

    tomorrow = datetime.now(UTC) + timedelta(days=1)
    if tx_dt > tomorrow:
        return "Дата и время не могут быть в будущем"

    return None


@main_bp.route("/transactions")
@login_required
def transactions_list():
    """
    Список транзакций с фильтрацией по дате, типу, валюте и проекту. Пагинация.
    """
    page = request.args.get("page", 1, type=int)
    per_page = 20
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    type_filter = request.args.get("type")
    currency_filter = request.args.get("currency")
    project_filter = request.args.get("project", type=int)

    query = Transaction.active()

    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=UTC)
            query = query.filter(Transaction.date >= date_from_obj)
        except ValueError:
            pass

    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").replace(
                tzinfo=UTC, hour=23, minute=59, second=59
            )
            query = query.filter(Transaction.date <= date_to_obj)
        except ValueError:
            pass

    if type_filter in ("income", "expense"):
        query = query.filter(Transaction.type == type_filter)

    if currency_filter in ("RUB", "USD", "EUR"):
        query = query.filter(Transaction.currency == currency_filter)

    if project_filter:
        query = query.filter(Transaction.project_id == project_filter)

    pagination = query.order_by(Transaction.date.desc(), Transaction.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    transactions = pagination.items

    income_categories = {c.id: c.name for c in IncomeCategory.query.all()}
    expense_categories = {c.id: c.name for c in ExpenseCategory.query.all()}

    all_projects_for_filter = Project.active().order_by(Project.name).all()
    currencies_for_filter = ["RUB", "USD", "EUR"]

    return render_template(
        "transactions/list.html",
        transactions=transactions,
        pagination=pagination,
        income_categories=income_categories,
        expense_categories=expense_categories,
        date_from=date_from,
        date_to=date_to,
        type_filter=type_filter,
        currency_filter=currency_filter,
        project_filter=project_filter,
        all_projects_for_filter=all_projects_for_filter,
        currencies_for_filter=currencies_for_filter,
    )


@main_bp.route("/transactions/create", methods=["GET", "POST"])
@login_required
def transaction_create():
    """
    Создание новой транзакции (доступно всем авторизованным пользователям).
    """
    form = TransactionForm()
    form.project_id.choices = [(p.id, p.name) for p in Project.active().all()]
    default_url = url_for("main.transactions_list")
    next_url = get_next_url(default_url)

    if request.method == "POST":
        t = request.form.get("type")
        set_category_choices(form, t)

        if form.validate_on_submit():
            project = db.session.get(Project, form.project_id.data)
            if not project:
                flash("Проект не найден", "danger")
                return redirect(url_for("main.transaction_create"))

            date_error = _validate_transaction_date(form, project)
            if date_error:
                flash(date_error, "danger")
                return render_template(
                    "transactions/create.html",
                    form=form,
                    income_categories=IncomeCategory.query.all(),
                    expense_categories=ExpenseCategory.query.all(),
                    next_url=next_url,
                )

            tx_date = form.date.data
            if tx_date is None:
                tx_date = datetime.now(UTC)
            elif tx_date.tzinfo is None:
                tx_date = tx_date.replace(tzinfo=UTC)

            transaction = Transaction(
                project_id=form.project_id.data,
                type=form.type.data,
                category_id=form.category_id.data,
                amount=form.amount.data,
                currency=form.currency.data,
                description=form.description.data,
                date=tx_date,
            )
            try:
                db.session.add(transaction)
                db.session.commit()
                flash("Транзакция добавлена", "success")
                return safe_redirect(default_url)
            except Exception as e:
                db.session.rollback()
                flash(f"Ошибка при сохранении: {str(e)}", "danger")
        else:
            for field, errors in form.errors.items():
                for err in errors:
                    flash(f'Ошибка в поле "{field}": {err}', "danger")

    return render_template(
        "transactions/create.html",
        form=form,
        income_categories=IncomeCategory.query.all(),
        expense_categories=ExpenseCategory.query.all(),
        next_url=next_url,
    )


@main_bp.route("/transactions/<int:transaction_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def transaction_edit(transaction_id):
    """
    Редактирование транзакции (только для админов).
    Удалённые транзакции недоступны.
    """
    transaction = Transaction.active().filter_by(id=transaction_id).first_or_404()
    form = TransactionForm(obj=transaction)
    form.project_id.choices = [(p.id, p.name) for p in Project.active().all()]
    default_url = url_for("main.transactions_list")
    next_url = get_next_url(default_url)

    if request.method == "GET":
        form.type.data = transaction.type
        form.project_id.data = transaction.project_id
        form.category_id.data = transaction.category_id
        form.amount.data = str(transaction.amount)
        form.currency.data = transaction.currency or "RUB"
        form.description.data = transaction.description or ""
        form.date.data = transaction.date

        set_category_choices(form, transaction.type)

    if request.method == "POST":
        t = request.form.get("type")
        set_category_choices(form, t)

        if form.validate_on_submit():
            project = db.session.get(Project, form.project_id.data)
            if not project:
                flash("Проект не найден", "danger")
                return redirect(url_for("main.transaction_edit", transaction_id=transaction_id))

            date_error = _validate_transaction_date(form, project)
            if date_error:
                flash(date_error, "danger")
                return render_template(
                    "transactions/edit.html",
                    form=form,
                    transaction=transaction,
                    income_categories=IncomeCategory.query.all(),
                    expense_categories=ExpenseCategory.query.all(),
                    next_url=next_url,
                )

            transaction.type = form.type.data
            transaction.project_id = form.project_id.data
            transaction.category_id = form.category_id.data
            transaction.amount = form.amount.data
            transaction.currency = form.currency.data
            transaction.description = form.description.data
            if form.date.data:
                tx_dt = form.date.data
                if tx_dt.tzinfo is None:
                    tx_dt = tx_dt.replace(tzinfo=UTC)
                transaction.date = tx_dt
            try:
                db.session.commit()
                flash("Транзакция обновлена", "success")
                return safe_redirect(default_url)
            except Exception as e:
                db.session.rollback()
                flash(f"Ошибка при обновлении: {str(e)}", "danger")
        else:
            for field, errors in form.errors.items():
                for err in errors:
                    flash(f'Ошибка в поле "{field}": {err}', "danger")

    return render_template(
        "transactions/edit.html",
        form=form,
        transaction=transaction,
        income_categories=IncomeCategory.query.all(),
        expense_categories=ExpenseCategory.query.all(),
        next_url=next_url,
    )


@main_bp.route("/transactions/<int:transaction_id>/delete", methods=["POST"])
@login_required
@admin_required
def transaction_delete(transaction_id):
    """
    Soft delete транзакции (только для админов).
    """
    transaction = Transaction.query.get_or_404(transaction_id)
    try:
        transaction.is_deleted = True
        db.session.commit()
        flash("Транзакция удалена", "warning")
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка при удалении: {str(e)}", "danger")
    return safe_redirect(url_for("main.transactions_list"))


@main_bp.route("/transactions/export")
@login_required
def export_transactions_csv():
    """
    Экспорт всех активных транзакций в CSV.
    """
    transactions = Transaction.active().order_by(Transaction.date.desc()).all()
    income_categories = {c.id: c.name for c in IncomeCategory.query.all()}
    expense_categories = {c.id: c.name for c in ExpenseCategory.query.all()}

    si = StringIO()
    writer = csv.writer(si, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(
        [
            "ID",
            "Дата",
            "Проект",
            "Тип",
            "Категория",
            "Сумма",
            "Валюта",
            "Сумма (RUB)",
            "Описание",
        ]
    )

    for t in transactions:
        category_name = (
            income_categories.get(t.category_id, "")
            if t.type == "income"
            else expense_categories.get(t.category_id, "")
        )

        writer.writerow(
            [
                t.id,
                t.date.strftime("%d.%m.%Y") if t.date else "",
                t.project.name if t.project else "",
                "Доход" if t.type == "income" else "Расход",
                category_name,
                round(t.amount, 2),
                t.currency or "RUB",
                t.amount_rub,
                t.description or "",
            ]
        )

    csv_content = si.getvalue()
    si.close()
    return make_csv_response(csv_content, "transactions_export.csv")
