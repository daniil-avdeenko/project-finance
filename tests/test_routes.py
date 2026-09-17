"""
Тесты маршрутов: доступ, CRUD, фильтры, экспорт.
"""

from app import db as _db
from app.models import Employee, ExpenseCategory, IncomeCategory, Project, Transaction

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
    """Удаление проекта также удаляет его транзакции (каскад)."""
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
        assert _db.session.get(Project, project_id) is None
        assert Transaction.query.count() == 0


# ============================================================
#   CRUD СОТРУДНИКОВ
# ============================================================


def test_edit_employee_with_projects(auth_client, app):
    """Редактирование сотрудника с привязкой проектов через project_ids."""
    with app.app_context():
        project1 = Project(name="Проект 1")
        project2 = Project(name="Проект 2")
        employee = Employee(name="Петров Пётр Петрович", position="Разработчик")
        _db.session.add_all([project1, project2, employee])
        _db.session.commit()
        emp_id = employee.id
        p1_id, p2_id = project1.id, project2.id

    response = auth_client.post(
        f"/employees/{emp_id}/edit",
        data={
            "name": "Петров Пётр Петрович",
            "position": "Старший разработчик",
            "phone": "+79990000000",
            "email": "petrov@test.ru",
            "project_ids": f"{p1_id},{p2_id}",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        updated = _db.session.get(Employee, emp_id)
        assert len(updated.projects) == 2
        assert updated.position == "Старший разработчик"


def test_delete_employee(auth_client, app):
    """Удаление сотрудника работает."""
    with app.app_context():
        employee = Employee(name="Иванов Иван Иванович", position="Разработчик")
        _db.session.add(employee)
        _db.session.commit()
        emp_id = employee.id

    response = auth_client.post(f"/employees/{emp_id}/delete", follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        assert _db.session.get(Employee, emp_id) is None


# ============================================================
#   CRUD ТРАНЗАКЦИЙ
# ============================================================


def test_edit_transaction(auth_client, app):
    """Редактирование транзакции меняет сумму и описание."""
    with app.app_context():
        project = Project(name="Проект")
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
            "date": "2026-09-12",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        updated = _db.session.get(Transaction, t_id)
        assert updated.amount == 5000
        assert updated.description == "Новое описание"


def test_delete_transaction(auth_client, app):
    """Удаление транзакции работает."""
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
        assert _db.session.get(Transaction, t_id) is None
        assert Transaction.query.count() == 0


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
#   ФИЛЬТРЫ ТРАНЗАКЦИЙ
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
