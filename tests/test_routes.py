"""
Тесты маршрутов: доступ, CRUD, фильтры, экспорт.
"""

from datetime import UTC, date, datetime, timedelta

from app import db as _db
from app.models import Employee, ExpenseCategory, IncomeCategory, Project, Transaction
from app.services.currency_service import upsert_rates

# ============================================================
#   ОБЩИЕ СТРАНИЦЫ И ДОСТУП
# ============================================================


def test_index_requires_login(client):
    """Без логина главная страница перенаправляет на /login."""
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.location


def test_login_page_opens(client):
    """Страница логина открывается."""
    response = client.get("/login")
    assert response.status_code == 200


def test_404_page(auth_client):
    """Несуществующая страница возвращает кастомную 404."""
    response = auth_client.get("/несуществующая-страница")
    assert response.status_code == 404
    assert "Страница не найдена".encode() in response.data


def test_dashboard_loads(auth_client):
    """Дашборд открывается и показывает ключевые блоки."""
    response = auth_client.get("/")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Дашборд" in text
    assert "Доходы" in text
    assert "Расходы" in text
    assert "Прибыль" in text


def test_chart_returns_data(auth_client, app):
    """График открывается, данные о проектах передаются в шаблон."""
    with app.app_context():
        project = Project(name="Проект для графика")
        _db.session.add(project)
        _db.session.commit()

    response = auth_client.get("/chart")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Проект для графика" in text


def test_dashboard_ignores_transactions_of_deleted_projects(auth_client, app):
    """Транзакции удалённых проектов не учитываются на дашборде."""
    from datetime import UTC, datetime

    with app.app_context():
        active_project = Project(name="Active")
        deleted_project = Project(name="Deleted", is_deleted=True)
        cat = IncomeCategory(name="I")
        _db.session.add_all([active_project, deleted_project, cat])
        _db.session.commit()

        # Активная транзакция: 1000
        _db.session.add(
            Transaction(
                project_id=active_project.id,
                type="income",
                category_id=cat.id,
                amount=1000,
                currency="RUB",
                date=datetime(2026, 9, 1, tzinfo=UTC),
            )
        )
        # Транзакция удалённого проекта: 5000 — не должна попасть
        _db.session.add(
            Transaction(
                project_id=deleted_project.id,
                type="income",
                category_id=cat.id,
                amount=5000,
                currency="RUB",
                is_deleted=False,
                date=datetime(2026, 9, 1, tzinfo=UTC),
            )
        )
        _db.session.commit()

    response = auth_client.get("/")
    text = response.get_data(as_text=True)

    assert "1 000" in text
    assert "6 000" not in text
    assert "5 000" not in text


# ============================================================
#   СПИСКИ ДЛЯ АДМИНА
# ============================================================


def test_projects_list_authorized(auth_client):
    """Авторизованный админ видит список проектов."""
    response = auth_client.get("/projects")
    assert response.status_code == 200
    assert "Проекты".encode() in response.data


def test_transactions_list_authorized(auth_client):
    """Админ видит список транзакций."""
    response = auth_client.get("/transactions")
    assert response.status_code == 200
    assert "Транзакции".encode() in response.data


def test_employees_list_authorized(auth_client):
    """Админ видит список сотрудников."""
    response = auth_client.get("/employees")
    assert response.status_code == 200
    assert "Сотрудники".encode() in response.data


def test_income_categories_authorized(auth_client):
    """Админ видит страницу категорий доходов."""
    response = auth_client.get("/income-categories")
    assert response.status_code == 200
    assert "Категории доходов" in response.get_data(as_text=True)


def test_expense_categories_authorized(auth_client):
    """Админ видит страницу категорий расходов."""
    response = auth_client.get("/expense-categories")
    assert response.status_code == 200
    assert "Категории расходов" in response.get_data(as_text=True)


def test_chart_authorized(auth_client):
    """Админ видит страницу графика."""
    response = auth_client.get("/chart")
    assert response.status_code == 200
    assert "Динамика рентабельности" in response.get_data(as_text=True)


def test_admin_sees_create_project_button(auth_client):
    """Админ видит кнопку «Создать проект»."""
    response = auth_client.get("/projects")
    assert response.status_code == 200
    assert "Создать проект" in response.get_data(as_text=True)


def test_user_does_not_see_create_button(regular_client):
    """Обычный пользователь НЕ видит кнопку «Создать проект»."""
    response = regular_client.get("/projects")
    assert response.status_code == 200
    assert "Создать проект" not in response.get_data(as_text=True)


# ============================================================
#   CRUD ПРОЕКТОВ
# ============================================================


def test_edit_project(auth_client, app):
    """Редактирование проекта меняет название и описание."""
    with app.app_context():
        project = Project(name="Старое название", description="Старое описание")
        _db.session.add(project)
        _db.session.commit()
        project_id = project.id

    response = auth_client.post(
        f"/projects/{project_id}/edit",
        data={"name": "Новое название", "description": "Новое описание"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        updated = _db.session.get(Project, project_id)
        assert updated.name == "Новое название"
        assert updated.description == "Новое описание"


def test_delete_project(auth_client, app):
    """Soft delete: проект остаётся в БД, но помечен is_deleted."""
    with app.app_context():
        project = Project(name="Удаляемый проект")
        category = IncomeCategory(name="Доход")
        _db.session.add_all([project, category])
        _db.session.commit()

        _db.session.add(
            Transaction(
                project_id=project.id,
                type="income",
                category_id=category.id,
                amount=1000,
            )
        )
        _db.session.commit()
        project_id = project.id

    response = auth_client.post(f"/projects/{project_id}/delete", follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        p = _db.session.get(Project, project_id)
        assert p is not None, "физически удалён"
        assert p.is_deleted is True
        assert Project.active().filter_by(id=project_id).first() is None


def test_deleted_project_not_in_dashboard(auth_client, app):
    """Удалённый проект не появляется на дашборде."""
    with app.app_context():
        project = Project(name="Скрытый проект", is_deleted=True)
        _db.session.add(project)
        _db.session.commit()

    response = auth_client.get("/")
    text = response.get_data(as_text=True)
    assert "Скрытый проект" not in text


# ============================================================
#   CRUD СОТРУДНИКОВ
# ============================================================


def test_edit_employee_with_projects(auth_client, app):
    """Редактирование сотрудника с привязкой проектов через project_roles."""
    import json

    with app.app_context():
        project1 = Project(name="Проект 1")
        project2 = Project(name="Проект 2")
        employee = Employee(name="Петров Пётр Петрович")
        _db.session.add_all([project1, project2, employee])
        _db.session.commit()
        emp_id = employee.id
        p1_id, p2_id = project1.id, project2.id

    project_roles = json.dumps(
        [
            {"project_id": p1_id, "role": "Разработчик"},
            {"project_id": p2_id, "role": "Тимлид"},
        ]
    )

    response = auth_client.post(
        f"/employees/{emp_id}/edit",
        data={
            "name": "Петров Пётр Петрович",
            "phone": "+79990000000",
            "email": "petrov@test.ru",
            "project_roles": project_roles,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        from app.models import EmployeeProject

        updated = _db.session.get(Employee, emp_id)
        assert len(updated.project_roles) == 2
        roles = {er.project_id: er.role for er in updated.project_roles}
        assert roles[p1_id] == "Разработчик"
        assert roles[p2_id] == "Тимлид"
        assert EmployeeProject.query.count() == 2


def test_delete_employee(auth_client, app):
    """Удаление сотрудника работает."""
    with app.app_context():
        employee = Employee(name="Иванов Иван Иванович")
        _db.session.add(employee)
        _db.session.commit()
        emp_id = employee.id

    response = auth_client.post(f"/employees/{emp_id}/delete", follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        assert _db.session.get(Employee, emp_id) is None


def test_create_employee_with_project_roles(auth_client, app):
    """Создание сотрудника с привязкой проектов и ролями через project_roles."""
    import json

    with app.app_context():
        project = Project(name="CRM")
        _db.session.add(project)
        _db.session.commit()
        p_id = project.id

    project_roles = json.dumps([{"project_id": p_id, "role": "Разработчик"}])

    response = auth_client.post(
        "/employees/create",
        data={
            "name": "Новый Сотрудник",
            "phone": "+79990000001",
            "email": "new@test.ru",
            "project_roles": project_roles,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        emp = Employee.query.filter_by(name="Новый Сотрудник").first()
        assert emp is not None
        assert len(emp.project_roles) == 1
        assert emp.project_roles[0].role == "Разработчик"
        assert emp.project_roles[0].project_id == p_id


def test_create_employee_skips_entries_without_role(auth_client, app):
    """Записи без роли игнорируются при создании."""
    import json

    with app.app_context():
        project = Project(name="CRM")
        _db.session.add(project)
        _db.session.commit()
        p_id = project.id

    project_roles = json.dumps(
        [
            {"project_id": p_id, "role": ""},  # пустая роль — пропускается
            {"project_id": p_id, "role": "  "},  # пробелы — пропускается
        ]
    )

    auth_client.post(
        "/employees/create",
        data={
            "name": "Без Роли",
            "project_roles": project_roles,
        },
        follow_redirects=True,
    )

    with app.app_context():
        emp = Employee.query.filter_by(name="Без Роли").first()
        assert emp is not None
        assert len(emp.project_roles) == 0


def test_employee_list_filters_by_role(auth_client, app):
    """Фильтр по роли оставляет только сотрудников с этой ролью."""
    with app.app_context():
        p = Project(name="P")
        e1 = Employee(name="Разработчик Иванов")
        e2 = Employee(name="Тимлид Петров")
        _db.session.add_all([p, e1, e2])
        _db.session.commit()

        from app.models import EmployeeProject

        _db.session.add_all(
            [
                EmployeeProject(employee_id=e1.id, project_id=p.id, role="Разработчик"),
                EmployeeProject(employee_id=e2.id, project_id=p.id, role="Тимлид"),
            ]
        )
        _db.session.commit()

    response = auth_client.get("/employees?role=Разработчик")
    text = response.get_data(as_text=True)

    assert "Разработчик Иванов" in text
    assert "Тимлид Петров" not in text


def test_api_roles_returns_unique_roles(auth_client, app):
    """API /api/roles возвращает уникальные роли."""
    with app.app_context():
        p = Project(name="P")
        e1 = Employee(name="A")
        e2 = Employee(name="B")
        _db.session.add_all([p, e1, e2])
        _db.session.commit()

        from app.models import EmployeeProject

        _db.session.add_all(
            [
                EmployeeProject(employee_id=e1.id, project_id=p.id, role="Разработчик"),
                EmployeeProject(employee_id=e2.id, project_id=p.id, role="Тимлид"),
            ]
        )
        _db.session.commit()

    response = auth_client.get("/api/roles")
    assert response.status_code == 200

    data = response.get_json()
    assert isinstance(data, list)
    assert "Разработчик" in data
    assert "Тимлид" in data


def test_api_roles_updates_after_new_role(auth_client, app):
    """После создания сотрудника с новой ролью API возвращает её."""
    import json

    with app.app_context():
        p = Project(name="P")
        _db.session.add(p)
        _db.session.commit()
        p_id = p.id

    # Изначально ролей нет
    response = auth_client.get("/api/roles")
    assert response.get_json() == []

    # Создаём сотрудника с новой ролью
    auth_client.post(
        "/employees/create",
        data={
            "name": "Маркетолог Тестов",
            "project_roles": json.dumps([{"project_id": p_id, "role": "Маркетолог"}]),
        },
        follow_redirects=True,
    )

    # Теперь роль есть в API
    response = auth_client.get("/api/roles")
    assert "Маркетолог" in response.get_json()


# ============================================================
#   CRUD ТРАНЗАКЦИЙ
# ============================================================


def test_edit_transaction(auth_client, app):
    """Редактирование транзакции меняет сумму и описание."""
    with app.app_context():
        project = Project(
            name="Проект",
            created_at=datetime.now(UTC) - timedelta(days=30),
        )
        category = IncomeCategory(name="Доход")
        _db.session.add_all([project, category])
        _db.session.commit()

        transaction = Transaction(
            project_id=project.id,
            type="income",
            category_id=category.id,
            amount=1000,
            description="Старое описание",
        )
        _db.session.add(transaction)
        _db.session.commit()
        t_id = transaction.id
        p_id = project.id
        c_id = category.id

    response = auth_client.post(
        f"/transactions/{t_id}/edit",
        data={
            "type": "income",
            "project_id": p_id,
            "category_id": c_id,
            "amount": "5000",
            "currency": "RUB",
            "description": "Новое описание",
            "date": "2026-09-12T14:30",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        updated = _db.session.get(Transaction, t_id)
        assert updated.amount == 5000
        assert updated.description == "Новое описание"


def test_delete_transaction(auth_client, app):
    """Soft delete: транзакция остаётся в БД, но помечена is_deleted."""
    with app.app_context():
        project = Project(name="Проект")
        category = IncomeCategory(name="Доход")
        _db.session.add_all([project, category])
        _db.session.commit()

        transaction = Transaction(
            project_id=project.id, type="income", category_id=category.id, amount=1000
        )
        _db.session.add(transaction)
        _db.session.commit()
        t_id = transaction.id

    response = auth_client.post(f"/transactions/{t_id}/delete", follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        t = _db.session.get(Transaction, t_id)
        assert t is not None
        assert t.is_deleted is True
        assert Transaction.active().filter_by(id=t_id).first() is None


def test_deleted_transaction_not_in_totals(auth_client, app):
    """Удалённая транзакция не учитывается в прибыли проекта."""
    with app.app_context():
        project = Project(name="P")
        inc = IncomeCategory(name="I")
        _db.session.add_all([project, inc])
        _db.session.commit()

        # Активная: +1000
        _db.session.add(
            Transaction(
                project_id=project.id,
                type="income",
                category_id=inc.id,
                amount=1000,
                currency="RUB",
                date=datetime(2026, 9, 1, tzinfo=UTC),
            )
        )
        # Удалённая: +5000 (не должна влиять)
        _db.session.add(
            Transaction(
                project_id=project.id,
                type="income",
                category_id=inc.id,
                amount=5000,
                currency="RUB",
                is_deleted=True,
                date=datetime(2026, 9, 1, tzinfo=UTC),
            )
        )
        _db.session.commit()

    response = auth_client.get("/")
    text = response.get_data(as_text=True)

    # На дашборде сумма 1 000, не 6 000
    assert "1 000" in text
    assert "6 000" not in text


def test_transaction_create_rejects_deleted_project(auth_client, app):
    """Нельзя создать транзакцию для удалённого проекта."""
    from datetime import UTC, datetime

    with app.app_context():
        project = Project(name="Удалённый", is_deleted=True)
        cat = IncomeCategory(name="Доход")
        _db.session.add_all([project, cat])
        _db.session.commit()
        p_id = project.id
        c_id = cat.id

    auth_client.post(
        "/transactions/create",
        data={
            "type": "income",
            "project_id": p_id,
            "category_id": c_id,
            "amount": "1000",
            "currency": "RUB",
            "description": "к удалённому",
            "date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M"),
        },
        follow_redirects=True,
    )

    with app.app_context():
        assert Transaction.query.filter_by(project_id=p_id).count() == 0


# ============================================================
#   CRUD КАТЕГОРИЙ ДОХОДОВ
# ============================================================


def test_income_category_create_page_opens(auth_client):
    """Страница создания категории дохода открывается."""
    response = auth_client.get("/income-categories/create")
    assert response.status_code == 200
    assert "Создать категорию дохода" in response.get_data(as_text=True)


def test_create_income_category_via_route(auth_client, app):
    """Создание категории дохода через POST."""
    response = auth_client.post(
        "/income-categories/create",
        data={"name": "Новая категория дохода"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        cat = IncomeCategory.query.filter_by(name="Новая категория дохода").first()
        assert cat is not None
        assert cat.name == "Новая категория дохода"


def test_income_category_edit_page_opens(auth_client, app):
    """Страница редактирования категории дохода открывается."""
    with app.app_context():
        category = IncomeCategory(name="Категория для редактирования")
        _db.session.add(category)
        _db.session.commit()
        c_id = category.id

    response = auth_client.get(f"/income-categories/{c_id}/edit")
    assert response.status_code == 200
    assert "Редактировать категорию" in response.get_data(as_text=True)


def test_edit_income_category(auth_client, app):
    """Редактирование категории дохода меняет название."""
    with app.app_context():
        category = IncomeCategory(name="Старое название дохода")
        _db.session.add(category)
        _db.session.commit()
        c_id = category.id

    response = auth_client.post(
        f"/income-categories/{c_id}/edit",
        data={"name": "Новое название дохода"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        updated = _db.session.get(IncomeCategory, c_id)
        assert updated.name == "Новое название дохода"


def test_delete_income_category(auth_client, app):
    """Удаление неиспользуемой категории дохода работает."""
    with app.app_context():
        category = IncomeCategory(name="Свободная категория")
        _db.session.add(category)
        _db.session.commit()
        c_id = category.id

    response = auth_client.post(f"/income-categories/{c_id}/delete", follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        assert _db.session.get(IncomeCategory, c_id) is None


def test_income_category_in_use_cannot_be_deleted(auth_client, app):
    """Категорию дохода, используемую в транзакции, удалить нельзя."""
    with app.app_context():
        project = Project(name="Проект")
        category = IncomeCategory(name="Занятая категория")
        _db.session.add_all([project, category])
        _db.session.commit()

        _db.session.add(
            Transaction(
                project_id=project.id,
                type="income",
                category_id=category.id,
                amount=5000,
            )
        )
        _db.session.commit()
        cat_id = category.id

    response = auth_client.post(f"/income-categories/{cat_id}/delete", follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        assert _db.session.get(IncomeCategory, cat_id) is not None


# ============================================================
#   CRUD КАТЕГОРИЙ РАСХОДОВ
# ============================================================


def test_expense_category_create_page_opens(auth_client):
    """Страница создания категории расхода открывается."""
    response = auth_client.get("/expense-categories/create")
    assert response.status_code == 200
    assert "Создать категорию расхода" in response.get_data(as_text=True)


def test_create_expense_category_via_route(auth_client, app):
    """Создание категории расхода через POST."""
    response = auth_client.post(
        "/expense-categories/create",
        data={"name": "Новая категория расхода"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        cat = ExpenseCategory.query.filter_by(name="Новая категория расхода").first()
        assert cat is not None
        assert cat.name == "Новая категория расхода"


def test_expense_category_edit_page_opens(auth_client, app):
    """Страница редактирования категории расхода открывается."""
    with app.app_context():
        category = ExpenseCategory(name="Категория для редактирования")
        _db.session.add(category)
        _db.session.commit()
        c_id = category.id

    response = auth_client.get(f"/expense-categories/{c_id}/edit")
    assert response.status_code == 200
    assert "Редактировать категорию" in response.get_data(as_text=True)


def test_edit_expense_category(auth_client, app):
    """Редактирование категории расхода меняет название."""
    with app.app_context():
        category = ExpenseCategory(name="Старое название")
        _db.session.add(category)
        _db.session.commit()
        c_id = category.id

    response = auth_client.post(
        f"/expense-categories/{c_id}/edit",
        data={"name": "Новое название"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        updated = _db.session.get(ExpenseCategory, c_id)
        assert updated.name == "Новое название"


def test_delete_expense_category(auth_client, app):
    """Удаление неиспользуемой категории расхода работает."""
    with app.app_context():
        category = ExpenseCategory(name="Свободная категория расхода")
        _db.session.add(category)
        _db.session.commit()
        c_id = category.id

    response = auth_client.post(f"/expense-categories/{c_id}/delete", follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        assert _db.session.get(ExpenseCategory, c_id) is None


# ============================================================
#   ТРАНЗАКЦИИ - ФИЛЬТРЫ И ДАТЫ
# ============================================================


def test_transactions_filter_by_type(auth_client, app):
    """Фильтрация транзакций по типу (income)."""
    with app.app_context():
        project = Project(name="Проект")
        cat = IncomeCategory(name="Доход")
        expense_cat = ExpenseCategory(name="Расход")
        _db.session.add_all([project, cat, expense_cat])
        _db.session.commit()

        _db.session.add(
            Transaction(project_id=project.id, type="income", category_id=cat.id, amount=1000)
        )
        _db.session.add(
            Transaction(
                project_id=project.id,
                type="expense",
                category_id=expense_cat.id,
                amount=2000,
            )
        )
        _db.session.commit()

    response = auth_client.get("/transactions?type=income")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "2 000" not in text or "Расход" not in text


def test_transactions_filter_by_date(auth_client, app):
    """Фильтрация транзакций по дате."""
    response = auth_client.get("/transactions?date_from=2026-01-01&date_to=2026-12-31")
    assert response.status_code == 200


def test_transactions_filter_by_currency(auth_client, app):
    """Фильтр по валюте оставляет только выбранную."""
    with app.app_context():
        project = Project(name="P")
        cat = IncomeCategory(name="I")
        _db.session.add_all([project, cat])
        _db.session.commit()

        _db.session.add_all(
            [
                Transaction(
                    project_id=project.id,
                    type="income",
                    category_id=cat.id,
                    amount=100,
                    currency="USD",
                    date=datetime(2026, 9, 1, tzinfo=UTC),
                ),
                Transaction(
                    project_id=project.id,
                    type="income",
                    category_id=cat.id,
                    amount=5000,
                    currency="RUB",
                    date=datetime(2026, 9, 1, tzinfo=UTC),
                ),
            ]
        )
        _db.session.commit()

    response = auth_client.get("/transactions?currency=USD")
    text = response.get_data(as_text=True)

    # Должна быть только USD-транзакция
    assert "100.00 USD" in text or "100 USD" in text
    # RUB-транзакция скрыта — проверяем, что 5000 не видно
    assert "5 000" not in text


def test_transactions_filter_by_project(auth_client, app):
    """Фильтр по проекту оставляет только транзакции этого проекта."""
    with app.app_context():
        p1 = Project(name="Проект-А")
        p2 = Project(name="Проект-Б")
        cat = IncomeCategory(name="I")
        _db.session.add_all([p1, p2, cat])
        _db.session.commit()

        _db.session.add_all(
            [
                Transaction(
                    project_id=p1.id,
                    type="income",
                    category_id=cat.id,
                    amount=1000,
                    currency="RUB",
                    date=datetime(2026, 9, 1, tzinfo=UTC),
                ),
                Transaction(
                    project_id=p2.id,
                    type="income",
                    category_id=cat.id,
                    amount=2000,
                    currency="RUB",
                    date=datetime(2026, 9, 1, tzinfo=UTC),
                ),
            ]
        )
        _db.session.commit()
        p1_id = p1.id

    response = auth_client.get(f"/transactions?project={p1_id}")
    text = response.get_data(as_text=True)

    # В отфильтрованном списке только транзакция Проект-А (сумма 1 000.00)
    assert "1 000.00" in text
    # Транзакции Проект-Б (сумма 2 000.00) в списке нет
    assert "2 000.00" not in text


def test_transaction_create_rejects_future_date(auth_client, app):
    """Дата и время транзакции не могут быть в будущем."""
    with app.app_context():
        start = datetime.now(UTC) - timedelta(days=30)
        project = Project(name="P", created_at=start)
        cat = IncomeCategory(name="Доход")
        _db.session.add_all([project, cat])
        _db.session.commit()
        p_id = project.id
        c_id = cat.id

    future_date = (datetime.now(UTC) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M")

    auth_client.post(
        "/transactions/create",
        data={
            "type": "income",
            "project_id": p_id,
            "category_id": c_id,
            "amount": "1000",
            "currency": "RUB",
            "description": "future",
            "date": future_date,
        },
        follow_redirects=True,
    )

    with app.app_context():
        assert Transaction.query.count() == 0


def test_transaction_create_rejects_date_before_project(auth_client, app):
    """Дата и время транзакции не могут быть раньше создания проекта."""
    with app.app_context():
        old_date = datetime.now(UTC) - timedelta(days=30)
        project = Project(name="P", created_at=old_date)
        cat = IncomeCategory(name="Доход")
        _db.session.add_all([project, cat])
        _db.session.commit()
        p_id = project.id
        c_id = cat.id

    earlier = (old_date - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M")

    auth_client.post(
        "/transactions/create",
        data={
            "type": "income",
            "project_id": p_id,
            "category_id": c_id,
            "amount": "1000",
            "currency": "RUB",
            "description": "before",
            "date": earlier,
        },
        follow_redirects=True,
    )

    with app.app_context():
        assert Transaction.query.count() == 0


def test_transaction_create_accepts_valid_date(auth_client, app):
    """Корректные дата и время (в пределах жизни проекта) — проходят."""
    with app.app_context():
        start = datetime.now(UTC) - timedelta(days=30)
        project = Project(name="P", created_at=start)
        cat = IncomeCategory(name="Доход")
        _db.session.add_all([project, cat])
        _db.session.commit()
        p_id = project.id
        c_id = cat.id

    valid_date = (datetime.now(UTC) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")

    auth_client.post(
        "/transactions/create",
        data={
            "type": "income",
            "project_id": p_id,
            "category_id": c_id,
            "amount": "1000",
            "currency": "RUB",
            "description": "valid",
            "date": valid_date,
        },
        follow_redirects=True,
    )

    with app.app_context():
        assert Transaction.query.count() == 1


# ============================================================
#   ЭКСПОРТ CSV
# ============================================================


def test_export_projects_csv(auth_client):
    """Экспорт проектов возвращает CSV-файл."""
    response = auth_client.get("/projects/export")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert "attachment" in response.headers["Content-Disposition"]


def test_export_employees_csv(auth_client):
    """Экспорт сотрудников возвращает CSV-файл."""
    response = auth_client.get("/employees/export")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"


def test_export_transactions_csv(auth_client):
    """Экспорт транзакций возвращает CSV-файл."""
    response = auth_client.get("/transactions/export")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"


def test_export_transactions_csv_includes_amount_rub(auth_client, app):
    """CSV-экспорт транзакций содержит колонку Сумма (RUB) в правильной позиции."""

    class FakeRate:
        def __init__(self, code, nominal, rate, rate_date):
            self.code = code
            self.nominal = nominal
            self.rate = rate
            self.rate_date = rate_date

    with app.app_context():
        upsert_rates([FakeRate("USD", 1, 84.50, date(2026, 9, 19))])

        project = Project(name="P")
        cat = IncomeCategory(name="C")
        _db.session.add_all([project, cat])
        _db.session.commit()

        _db.session.add(
            Transaction(
                project_id=project.id,
                type="income",
                category_id=cat.id,
                amount=100,
                currency="USD",
                date=datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
            )
        )
        _db.session.commit()

    response = auth_client.get("/transactions/export")
    text = response.get_data(as_text=True)

    # Заголовок содержит колонку Сумма (RUB)
    header_line = text.splitlines()[0]
    assert "Сумма (RUB)" in header_line

    cols = header_line.split(";")
    idx_amount = cols.index("Сумма")
    idx_currency = cols.index("Валюта")
    idx_amount_rub = cols.index("Сумма (RUB)")
    idx_description = cols.index("Описание")

    assert idx_amount < idx_currency < idx_amount_rub < idx_description

    # Данные: одна транзакция, проверяем значение в колонке Сумма (RUB)
    data_line = text.splitlines()[1]
    cells = data_line.split(";")
    assert cells[idx_amount_rub] == "8450.0"


# ============================================================
#   КОНВЕРТАЦИЯ И КУРС ВАЛЮТ
# ============================================================


def test_dashboard_converts_usd_to_rub(auth_client, app):
    """Дашборд считает доход в рублях при USD-транзакции."""

    class FakeRate:
        def __init__(self, code, nominal, rate, rate_date):
            self.code = code
            self.nominal = nominal
            self.rate = rate
            self.rate_date = rate_date

    with app.app_context():
        upsert_rates([FakeRate("USD", 1, 84.50, date(2026, 9, 19))])

        project = Project(name="P")
        cat = IncomeCategory(name="C")
        _db.session.add_all([project, cat])
        _db.session.commit()

        _db.session.add(
            Transaction(
                project_id=project.id,
                type="income",
                category_id=cat.id,
                amount=100,
                currency="USD",
                date=datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
            )
        )
        _db.session.commit()

    response = auth_client.get("/")
    text = response.get_data(as_text=True)

    # 100 USD * 84.50 = 8450 RUB — money-фильтр выводит "8 450.00"
    assert "8 450.00" in text


def test_dashboard_shows_currency_rates(auth_client, app):
    """Дашборд показывает актуальные курсы USD и EUR из БД."""

    class FakeRate:
        def __init__(self, code, nominal, rate, rate_date):
            self.code = code
            self.nominal = nominal
            self.rate = rate
            self.rate_date = rate_date

    with app.app_context():
        upsert_rates(
            [
                FakeRate("USD", 1, 84.50, date(2026, 9, 19)),
                FakeRate("EUR", 1, 97.30, date(2026, 9, 19)),
            ]
        )

    response = auth_client.get("/")
    text = response.get_data(as_text=True)

    assert "84.50" in text or "84,50" in text or "84 500" in text
    assert "97.30" in text or "97,30" in text
