import csv
import json
from io import StringIO

from flask import flash, jsonify, render_template, request, url_for
from flask_login import login_required

from app import db
from app.decorators import admin_required
from app.forms import EmployeeForm
from app.helpers import get_next_url, make_csv_response, safe_redirect
from app.models import Employee, EmployeeProject, Project
from app.routes.blueprint import main_bp
from app.services.excel_export import build_employees_workbook, make_xlsx_response


def parse_project_roles(project_roles_json: str) -> list[dict]:
    """
    Разбирает JSON со списком привязок сотрудника к проектам.

    Ожидаемый формат: '[{"project_id": 1, "role": "Разработчик"}, ...]'
    Возвращает список словарей. Игнорирует некорректные элементы и пустые роли.
    """
    if not project_roles_json:
        return []
    try:
        data = json.loads(project_roles_json)
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(data, list):
        return []

    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("project_id")
        if raw_id is None:
            continue
        try:
            project_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        role = (item.get("role") or "").strip()
        if not role:
            continue
        result.append({"project_id": project_id, "role": role})
    return result


@main_bp.route("/employees")
@login_required
def employees_list():
    """
    Список сотрудников с фильтрацией по роли на проекте и сортировкой.

    Фильтр по роли: оставляет сотрудников, у которых есть эта роль
    хотя бы на одном проекте. Список ролей — уникальные значения из
    EmployeeProject.role.
    """
    query = Employee.query

    role_filter = request.args.get("role")
    if role_filter:
        subq = (
            db.session.query(EmployeeProject.employee_id)
            .filter(EmployeeProject.role == role_filter)
            .distinct()
            .subquery()
        )
        query = query.filter(Employee.id.in_(db.session.query(subq.c.employee_id)))

    employees = query.all()

    sort = request.args.get("sort", "name_asc")
    if sort == "name_asc":
        employees.sort(key=lambda e: e.name)
    elif sort == "name_desc":
        employees.sort(key=lambda e: e.name, reverse=True)
    elif sort == "projects_asc":
        employees.sort(key=lambda e: len(e.project_roles))
    elif sort == "projects_desc":
        employees.sort(key=lambda e: len(e.project_roles), reverse=True)

    roles = (
        db.session.query(EmployeeProject.role)
        .filter(EmployeeProject.role.isnot(None))
        .filter(EmployeeProject.role != "")
        .distinct()
        .order_by(EmployeeProject.role)
        .all()
    )
    roles = [r[0] for r in roles if r[0]]

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
        roles=roles,
        selected_role=role_filter,
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
            phone=form.phone.data,
            email=form.email.data,
        )

        project_roles = parse_project_roles(request.form.get("project_roles", ""))
        try:
            db.session.add(employee)
            db.session.flush()  # получаем employee.id

            for pr in project_roles:
                project = Project.active().filter_by(id=pr["project_id"]).first()
                if not project:
                    continue
                db.session.add(
                    EmployeeProject(
                        employee_id=employee.id,
                        project_id=project.id,
                        role=pr["role"],
                    )
                )

            db.session.commit()
            flash("Сотрудник добавлен!", "success")
            return safe_redirect(default_url)
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при сохранении: {str(e)}", "danger")

    all_roles = (
        db.session.query(EmployeeProject.role)
        .filter(EmployeeProject.role != "")
        .distinct()
        .order_by(EmployeeProject.role)
        .all()
    )
    all_roles = [r[0] for r in all_roles]

    return render_template(
        "employees/create.html",
        form=form,
        all_projects=Project.active().all(),
        all_roles=all_roles,
        next_url=next_url,
    )


@main_bp.route("/employees/<int:employee_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def employee_edit(employee_id):
    """Редактирование сотрудника (только для админов)."""
    employee = Employee.query.get_or_404(employee_id)
    form = EmployeeForm(obj=employee)
    default_url = url_for("main.employee_detail", employee_id=employee.id)
    next_url = get_next_url(default_url)

    if request.method == "GET":
        current_roles = [
            {"project_id": er.project_id, "role": er.role} for er in employee.project_roles
        ]
        all_roles = (
            db.session.query(EmployeeProject.role)
            .filter(EmployeeProject.role != "")
            .distinct()
            .order_by(EmployeeProject.role)
            .all()
        )
        all_roles = [r[0] for r in all_roles]

        return render_template(
            "employees/edit.html",
            form=form,
            employee=employee,
            all_projects=Project.active().all(),
            all_roles=all_roles,
            current_project_roles=current_roles,
            next_url=next_url,
        )

    if request.method == "POST" and form.validate_on_submit():
        employee.name = form.name.data
        employee.phone = form.phone.data
        employee.email = form.email.data

        project_roles = parse_project_roles(request.form.get("project_roles", ""))

        try:
            # Удаляем старые привязки и создаём новые
            EmployeeProject.query.filter_by(employee_id=employee.id).delete()

            for pr in project_roles:
                project = Project.active().filter_by(id=pr["project_id"]).first()
                if not project:
                    continue
                db.session.add(
                    EmployeeProject(
                        employee_id=employee.id,
                        project_id=project.id,
                        role=pr["role"],
                    )
                )

            db.session.commit()
            flash("Сотрудник обновлён", "success")
            return safe_redirect(default_url)
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при обновлении: {str(e)}", "danger")

    # Fallback при ошибке валидации
    current_roles = [
        {"project_id": er.project_id, "role": er.role} for er in employee.project_roles
    ]
    all_roles = (
        db.session.query(EmployeeProject.role)
        .filter(EmployeeProject.role != "")
        .distinct()
        .order_by(EmployeeProject.role)
        .all()
    )
    all_roles = [r[0] for r in all_roles]

    return render_template(
        "employees/edit.html",
        form=form,
        employee=employee,
        all_projects=Project.active().all(),
        all_roles=all_roles,
        current_project_roles=current_roles,
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
    """Экспорт всех сотрудников в CSV."""
    employees = Employee.query.all()
    si = StringIO()
    writer = csv.writer(si, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["ID", "ФИО", "Телефон", "Email", "Проекты и роли"])
    for emp in employees:
        project_roles = "; ".join(f"{er.project.name} — {er.role}" for er in emp.project_roles)
        writer.writerow(
            [
                emp.id,
                emp.name,
                emp.phone or "",
                emp.email or "",
                project_roles,
            ]
        )
    csv_content = si.getvalue()
    si.close()
    return make_csv_response(csv_content, "employees_export.csv")


@main_bp.route("/employees/export/xlsx")
@login_required
def export_employees_xlsx():
    """Экспорт всех сотрудников в Excel (.xlsx)."""
    employees = Employee.query.all()
    wb = build_employees_workbook(employees)
    return make_xlsx_response(wb, "employees_export.xlsx")


@main_bp.route("/api/roles")
@login_required
@admin_required
def api_roles():
    """
    API: возвращает список всех уникальных ролей из EmployeeProject.

    Используется формой сотрудника для обновления dropdown ролей
    по клику — чтобы новые роли появлялись без перезагрузки страницы.
    """
    roles = (
        db.session.query(EmployeeProject.role)
        .filter(EmployeeProject.role.isnot(None))
        .filter(EmployeeProject.role != "")
        .distinct()
        .order_by(EmployeeProject.role)
        .all()
    )
    return jsonify([r[0] for r in roles if r[0]])
