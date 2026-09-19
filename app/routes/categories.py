from flask import flash, redirect, render_template, url_for
from flask_login import login_required

from app import db
from app.decorators import admin_required
from app.forms import ExpenseCategoryForm, IncomeCategoryForm
from app.models import ExpenseCategory, IncomeCategory, Transaction
from app.routes.blueprint import main_bp


# ===== ДОХОДЫ =====
@main_bp.route("/income-categories")
@login_required
def income_categories_list():
    """Список всех категорий доходов."""
    categories = IncomeCategory.query.all()
    return render_template("categories/income.html", categories=categories)


@main_bp.route("/income-categories/create", methods=["GET", "POST"])
@login_required
@admin_required
def income_category_create():
    """Создание новой категории дохода (только для админов)."""
    form = IncomeCategoryForm()
    if form.validate_on_submit():
        category = IncomeCategory(name=form.name.data)
        db.session.add(category)
        db.session.commit()
        flash("Категория дохода добавлена", "success")
        return redirect(url_for("main.income_categories_list"))
    return render_template("categories/create_income.html", form=form)


@main_bp.route("/income-categories/<int:category_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def income_category_edit(category_id):
    """Редактирование категории дохода (только для админов)."""
    category = IncomeCategory.query.get_or_404(category_id)
    form = IncomeCategoryForm(obj=category)
    if form.validate_on_submit():
        category.name = form.name.data
        db.session.commit()
        flash("Категория обновлена", "success")
        return redirect(url_for("main.income_categories_list"))
    return render_template("categories/edit.html", form=form, category=category)


@main_bp.route("/income-categories/<int:category_id>/delete", methods=["POST"])
@login_required
@admin_required
def income_category_delete(category_id):
    """
    Удаление категории дохода (только для админов).
    Запрещено, если категория используется в активных транзакциях.
    """
    category = IncomeCategory.query.get_or_404(category_id)
    # Проверка использования в АКТИВНЫХ транзакциях
    if Transaction.active().filter_by(category_id=category_id, type="income").first():
        flash("Нельзя удалить категорию, так как она используется в транзакциях", "danger")
        return redirect(url_for("main.income_categories_list"))
    db.session.delete(category)
    db.session.commit()
    flash("Категория удалена", "warning")
    return redirect(url_for("main.income_categories_list"))


# ===== РАСХОДЫ =====
@main_bp.route("/expense-categories")
@login_required
def expense_categories_list():
    """Список всех категорий расходов."""
    categories = ExpenseCategory.query.all()
    return render_template("categories/expense.html", categories=categories)


@main_bp.route("/expense-categories/create", methods=["GET", "POST"])
@login_required
@admin_required
def expense_category_create():
    """Создание новой категории расхода (только для админов)."""
    form = ExpenseCategoryForm()
    if form.validate_on_submit():
        category = ExpenseCategory(name=form.name.data)
        db.session.add(category)
        db.session.commit()
        flash("Категория расхода добавлена", "success")
        return redirect(url_for("main.expense_categories_list"))
    return render_template("categories/create_expense.html", form=form)


@main_bp.route("/expense-categories/<int:category_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def expense_category_edit(category_id):
    """Редактирование категории расхода (только для админов)."""
    category = ExpenseCategory.query.get_or_404(category_id)
    form = ExpenseCategoryForm(obj=category)
    if form.validate_on_submit():
        category.name = form.name.data
        db.session.commit()
        flash("Категория обновлена", "success")
        return redirect(url_for("main.expense_categories_list"))
    return render_template("categories/edit.html", form=form, category=category)


@main_bp.route("/expense-categories/<int:category_id>/delete", methods=["POST"])
@login_required
@admin_required
def expense_category_delete(category_id):
    """
    Удаление категории расхода (только для админов).
    Запрещено, если категория используется в активных транзакциях.
    """
    category = ExpenseCategory.query.get_or_404(category_id)
    if Transaction.active().filter_by(category_id=category_id, type="expense").first():
        flash("Нельзя удалить категорию, так как она используется в транзакциях", "danger")
        return redirect(url_for("main.expense_categories_list"))
    db.session.delete(category)
    db.session.commit()
    flash("Категория удалена", "warning")
    return redirect(url_for("main.expense_categories_list"))
