import csv
import json
from io import StringIO

from flask import flash, render_template, request, url_for
from flask_login import login_required

from app import db
from app.decorators import admin_required
from app.forms import EmployeeForm
from app.helpers import get_next_url, make_csv_response, safe_redirect
from app.models import Employee, Project
from app.routes.blueprint import main_bp


def parse_project_ids(project_ids_str):
    """
    Преобразует строку с ID проектов (разделённых запятыми) в список целых чисел.
    Игнорирует пустые и нечисловые значения.
    """
    if not project_ids_str:
        return []
    ids = []
    for part in project_ids_str.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


@main_bp.route("/employees")
@login_required
def employees_list():
    """
    Список сотрудников с фильтрацией по должности и сортировкой.
    """
    query = Employee.query

    position = request.args.get("position")
    if position:
        query = query.filter(Employee.position == position)

    employees = query.all()

    sort = request.args.get("sort", "name_asc")
    if sort == "name_asc":
        employees.sort(key=lambda e: e.name)
    elif sort == "name_desc":
        employees.sort(key=lambda e: e.name, reverse=True)
    elif sort == "projects_asc":
        employees.sort(key=lambda e: len(e.projects))
    elif sort == "projects_desc":
        employees.sort(key=lambda e: len(e.projects), reverse=True)

    positions = db.session.query(Employee.position).distinct().all()
    positions = [p[0] for p in positions if p[0]]

    sort_options = [
        {"value": "name_asc", "label": "ФИО А–Я", "selected": sort == "name_asc"},
        {"value": "name_desc", "label": "ФИО Я–А", "selected": sort == "name_desc"},
        {
            "value": "projects_asc",
            "label": "По проектам (↑)",
            "selected": sort == "projects_asc",
        },
        {
            "value": "projects_desc",
            "label": "По проектам (↓)",
            "selected": sort == "projects_desc",
        },
    ]

    return render_template(
        "employees/list.html",
        employees=employees,
        positions=positions,
        selected_position=position,
        sort_options=sort_options,
    )


@main_bp.route("/employees/<int:employee_id>")
@login_required
def employee_detail(employee_id):
    """
    Карточка сотрудника с полной информацией.
    """
    employee = Employee.query.get_or_404(employee_id)
    return render_template("employees/detail.html", employee=employee)


@main_bp.route("/employees/create", methods=["GET", "POST"])
@login_required
@admin_required
def employee_create():
    """Создание нового сотрудника (только для админов)."""
    form = EmployeeForm()
    default_url = url_for("main.employees_list")
    next_url = get_next_url(default_url)

    if request.method == "POST" and form.validate_on_submit():
        employee = Employee(
            name=form.name.data,
            position=form.position.data,
            phone=form.phone.data,
            email=form.email.data,
        )
        project_ids = parse_project_ids(request.form.get("project_ids", ""))
        employee.projects = Project.active().filter(Project.id.in_(project_ids)).all()

        try:
            db.session.add(employee)
            db.session.commit()
            flash("Сотрудник добавлен!", "success")
            return safe_redirect(default_url)
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при сохранении: {str(e)}", "danger")

    return render_template(
        "employees/create.html",
        form=form,
        all_projects=Project.active().all(),
        next_url=next_url,
    )


@main_bp.route("/employees/<int:employee_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def employee_edit(employee_id):
    """
    Редактирование сотрудника (доступно только администраторам).
    """
    employee = Employee.query.get_or_404(employee_id)
    form = EmployeeForm(obj=employee)
    default_url = url_for("main.employee_detail", employee_id=employee.id)
    next_url = get_next_url(default_url)

    employee_projects_json = json.dumps(
        [{"id": p.id, "name": p.name} for p in employee.projects], ensure_ascii=False
    )

    if request.method == "GET":
        return render_template(
            "employees/edit.html",
            form=form,
            employee=employee,
            all_projects=Project.active().all(),
            employee_projects_json=employee_projects_json,
            next_url=next_url,
        )

    if request.method == "POST" and form.validate_on_submit():
        employee.name = form.name.data
        employee.position = form.position.data
        employee.phone = form.phone.data
        employee.email = form.email.data

        project_ids = parse_project_ids(request.form.get("project_ids", ""))
        employee.projects = Project.active().filter(Project.id.in_(project_ids)).all()

        try:
            db.session.commit()
            flash("Сотрудник обновлён", "success")
            return safe_redirect(default_url)
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при обновлении: {str(e)}", "danger")

    return render_template(
        "employees/edit.html",
        form=form,
        employee=employee,
        all_projects=Project.active().all(),
        employee_projects_json=employee_projects_json,
        next_url=next_url,
    )


@main_bp.route("/employees/<int:employee_id>/delete", methods=["POST"])
@login_required
@admin_required
def employee_delete(employee_id):
    """Удаление сотрудника (доступно только администраторам)."""
    employee = Employee.query.get_or_404(employee_id)
    try:
        db.session.delete(employee)
        db.session.commit()
        flash("Сотрудник удалён", "warning")
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка при удалении: {str(e)}", "danger")
    return safe_redirect(url_for("main.employees_list"))


@main_bp.route("/employees/export")
@login_required
def export_employees_csv():
    """
    Экспорт всех сотрудников в CSV-файл.
    """
    employees = Employee.query.all()
    si = StringIO()
    writer = csv.writer(si, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["ID", "ФИО", "Должность", "Телефон", "Email", "Проекты"])
    for emp in employees:
        projects_names = ", ".join([p.name for p in emp.projects])
        writer.writerow(
            [
                emp.id,
                emp.name,
                emp.position or "",
                emp.phone or "",
                emp.email or "",
                projects_names,
            ]
        )
    csv_content = si.getvalue()
    si.close()
    return make_csv_response(csv_content, "employees_export.csv")
