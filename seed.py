# seed.py
import os
import random
from datetime import UTC, datetime, timedelta

from app import create_app, db
from app.models import (
    Employee,
    ExpenseCategory,
    IncomeCategory,
    Project,
    Transaction,
    User,
)


def seed():
    os.environ["EVENTS_ENABLED"] = "false"
    app = create_app()
    with app.app_context():
        # ---------- 1. ПОЛЬЗОВАТЕЛИ ----------
        if not User.query.filter_by(username="admin").first():
            admin = User(username="admin", role="admin")
            admin.set_password("admin")
            db.session.add(admin)

        if not User.query.filter_by(username="user").first():
            user = User(username="user", role="user")
            user.set_password("user")
            db.session.add(user)

        db.session.commit()
        print("✅ Пользователи: admin/admin, user/user")

        # ---------- 2. КАТЕГОРИИ ----------
        IncomeCategory.query.delete()
        ExpenseCategory.query.delete()
        db.session.commit()

        income_names = [
            "Разработка ПО на заказ",
            "Продажа готового ПО",
            "Консультационные услуги",
            "Абонентское обслуживание",
            "Обучение и тренинги",
            "Интеграционные услуги",
            "Техническая поддержка",
        ]
        # Убрали «Дивиденды» (корпоративная статья, не проектная), добавили «Налоги и сборы»
        expense_names = [
            "Внешние программисты",
            "Внутренние программисты",
            "Расходы на ИИ",
            "Аренда сервера",
            "Маркетинг",
            "Командировки",
            "Юридические услуги",
            "Налоги и сборы",
            "Непредвиденные расходы",
        ]

        for name in income_names:
            db.session.add(IncomeCategory(name=name))
        for name in expense_names:
            db.session.add(ExpenseCategory(name=name))
        db.session.commit()
        print("✅ Категории созданы")

        income_cats = {c.name: c for c in IncomeCategory.query.all()}
        expense_cats = {c.name: c for c in ExpenseCategory.query.all()}

        # ---------- 3. ПРОЕКТЫ ----------
        # Реалистичные параметры: длительность 4–9 месяцев, доходы и расходы в месяц
        # Рентабельность каждого проекта в диапазоне 25–31%
        project_defs = [
            {
                "name": "CRM для банка «Альфа»",
                "description": "Разработка и внедрение CRM-системы для банка. Интеграция с телефонией и чат-ботами.",
                "income_cats": ["Разработка ПО на заказ", "Консультационные услуги"],
                "expense_cats": [
                    "Внутренние программисты",
                    "Внешние программисты",
                    "Аренда сервера",
                    "Маркетинг",
                    "Налоги и сборы",
                ],
                "target_income_month": 5300000,
                "target_expense_month": 3700000,
                "months_ago": 9,
            },
            {
                "name": "Интеграция 1С для сети «Бета»",
                "description": "Настройка обмена данными между 1С:Управление торговлей и Битрикс24.",
                "income_cats": ["Интеграционные услуги"],
                "expense_cats": [
                    "Внешние программисты",
                    "Командировки",
                    "Юридические услуги",
                    "Налоги и сборы",
                ],
                "target_income_month": 2600000,
                "target_expense_month": 1900000,
                "months_ago": 5,
            },
            {
                "name": "Мобильное приложение для доставки «Гамма»",
                "description": "Разработка мобильного приложения для заказа еды с интеграцией в CRM.",
                "income_cats": ["Разработка ПО на заказ"],
                "expense_cats": [
                    "Внутренние программисты",
                    "Расходы на ИИ",
                    "Маркетинг",
                    "Налоги и сборы",
                ],
                "target_income_month": 2800000,
                "target_expense_month": 2000000,
                "months_ago": 7,
            },
            {
                "name": "Облачная платформа IoT для «Дельта»",
                "description": "Создание облачной платформы для управления IoT-устройствами.",
                "income_cats": ["Продажа готового ПО", "Абонентское обслуживание"],
                "expense_cats": [
                    "Внутренние программисты",
                    "Аренда сервера",
                    "Расходы на ИИ",
                    "Налоги и сборы",
                ],
                "target_income_month": 3800000,
                "target_expense_month": 2750000,
                "months_ago": 8,
            },
            {
                "name": "Внедрение Битрикс24 для «Эпсилон»",
                "description": "Консалтинг, настройка и обучение работе с Битрикс24.",
                "income_cats": ["Консультационные услуги", "Обучение и тренинги"],
                "expense_cats": [
                    "Внутренние программисты",
                    "Командировки",
                    "Налоги и сборы",
                ],
                "target_income_month": 1950000,
                "target_expense_month": 1400000,
                "months_ago": 4,
            },
            {
                "name": "Техподдержка для «Зета»",
                "description": "Срочная техническая поддержка и доработки для крупного клиента.",
                "income_cats": ["Техническая поддержка"],
                "expense_cats": [
                    "Внутренние программисты",
                    "Внешние программисты",
                    "Налоги и сборы",
                ],
                "target_income_month": 1400000,
                "target_expense_month": 1000000,
                "months_ago": 4,
            },
        ]

        now = datetime.now(UTC)
        projects = []
        for p_def in project_defs:
            start = now - timedelta(days=p_def["months_ago"] * 30)
            p = Project(name=p_def["name"], description=p_def["description"], created_at=start)
            db.session.add(p)
            projects.append(p)
        db.session.commit()
        print(f"✅ {len(projects)} проектов создано")

        # ---------- 4. СОТРУДНИКИ (фиксированный список) ----------
        employees_data = [
            # Тимлиды
            ("Иванов Иван Иванович", "Тимлид"),
            ("Петрова Анна Сергеевна", "Старший разработчик"),
            ("Сидоров Сергей Сергеевич", "Старший разработчик"),
            ("Смирнова Елена Дмитриевна", "Старший разработчик"),
            # Разработчики
            ("Кузнецов Андрей Николаевич", "Разработчик"),
            ("Попова Мария Александровна", "Разработчик"),
            ("Лебедев Максим Игоревич", "Разработчик"),
            ("Соколова Ольга Викторовна", "Разработчик"),
            ("Морозов Никита Павлович", "Разработчик"),
            ("Волкова Татьяна Романовна", "Разработчик"),
            # Тимлиды
            ("Козлов Владимир Олегович", "Тимлид"),
            ("Новикова Ирина Евгеньевна", "Тимлид"),
            # Аналитики
            ("Громов Станислав Юрьевич", "Аналитик"),
            ("Фёдорова Екатерина Максимовна", "Аналитик"),
            ("Михайлов Денис Валерьевич", "Аналитик"),
            # DevOps
            ("Алексеева Наталья Анатольевна", "DevOps-инженер"),
            ("Васильев Олег Дмитриевич", "DevOps-инженер"),
            # Менеджеры проектов
            ("Орлов Виктор Сергеевич", "Менеджер проектов"),
            ("Титов Павел Андреевич", "Менеджер проектов"),
            ("Медведева Галина Игоревна", "Менеджер проектов"),
            # Консультанты
            ("Белов Юрий Владимирович", "Консультант"),
            ("Гаврилов Константин Петрович", "Консультант"),
            # Тестировщик / поддержка
            ("Андреева Светлана Николаевна", "Тестировщик"),
            ("Фомин Григорий Семёнович", "Инженер поддержки"),
            ("Борисова Ксения Артёмовна", "Инженер поддержки"),
            # Внешние разработчики
            ("Шмидт Андрей Викторович", "Внешний разработчик"),
            ("Мюллер Елена Александровна", "Внешний разработчик"),
            ("Фишер Павел Дмитриевич", "Внешний разработчик"),
            ("Вебер Ольга Сергеевна", "Внешний разработчик"),
            ("Краузе Игорь Николаевич", "Внешний разработчик"),
        ]

        employees = []
        for name, position in employees_data:
            email_prefix = name.lower().replace(" ", ".")
            domain = "@external.com" if "Внешний" in position else "@company.ru"
            emp = Employee(
                name=name,
                position=position,
                phone=f"+7 999 {random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(10, 99)}",
                email=email_prefix + domain,
            )
            employees.append(emp)
            db.session.add(emp)
        db.session.commit()
        print(f"✅ {len(employees)} сотрудников создано")

        # ---------- 5. РАСПРЕДЕЛЕНИЕ ПО ПРОЕКТАМ ----------
        # Каждый сотрудник — максимум на 2 проектах
        assignments = {
            0: [0, 1, 2, 4, 5, 12, 15, 17, 22, 25, 26],  # CRM Альфа — 11 чел
            1: [3, 6, 7, 13, 18, 27],  # 1С Бета — 6 чел
            2: [10, 8, 9, 14, 19, 28],  # Мобильное Гамма — 6 чел
            3: [11, 1, 2, 6, 16, 19, 21],  # Облачная Дельта — 7 чел
            4: [4, 17, 20, 21],  # Битрикс Эпсилон — 4 чел
            5: [9, 23, 24, 29],  # Техподдержка Зета — 4 чел
        }

        for proj_idx, emp_indices in assignments.items():
            project = projects[proj_idx]
            for idx in emp_indices:
                project.employees.append(employees[idx])
        db.session.commit()
        print("✅ Сотрудники распределены по проектам")

        # ---------- 6. ТРАНЗАКЦИИ ----------
        for proj_idx, project in enumerate(projects):
            p_def = project_defs[proj_idx]
            start_date = project.created_at.replace(tzinfo=UTC)
            end_date = now

            current = start_date
            while current < end_date:
                next_month = current.replace(day=28) + timedelta(days=4)
                next_month = next_month.replace(day=1)

                target_income = p_def["target_income_month"]
                target_expense = p_def["target_expense_month"]

                num_income = random.randint(3, 5)
                num_expense = random.randint(4, 6)

                income_cats_for_proj = [income_cats[name] for name in p_def["income_cats"]]
                for _ in range(num_income):
                    cat = random.choice(income_cats_for_proj)
                    amount = round(target_income / num_income * random.uniform(0.7, 1.3), 2)
                    day = random.randint(1, 28)
                    t_date = current.replace(day=min(day, 28)) + timedelta(
                        days=random.randint(0, 2)
                    )
                    t_date = t_date.replace(
                        hour=random.randint(9, 17), minute=random.choice([0, 30])
                    )
                    if t_date > end_date:
                        t_date = end_date - timedelta(days=1)
                    desc = f"Поступление по {cat.name}"
                    transaction = Transaction(
                        project_id=project.id,
                        type="income",
                        category_id=cat.id,
                        amount=amount,
                        currency="RUB",
                        description=desc,
                        date=t_date,
                    )
                    db.session.add(transaction)

                expense_cats_for_proj = [expense_cats[name] for name in p_def["expense_cats"]]
                for _ in range(num_expense):
                    cat = random.choice(expense_cats_for_proj)
                    amount = round(target_expense / num_expense * random.uniform(0.7, 1.3), 2)
                    day = random.randint(1, 28)
                    t_date = current.replace(day=min(day, 28)) + timedelta(
                        days=random.randint(0, 2)
                    )
                    t_date = t_date.replace(
                        hour=random.randint(9, 17), minute=random.choice([0, 30])
                    )
                    if t_date > end_date:
                        t_date = end_date - timedelta(days=1)
                    desc = f"Оплата по {cat.name}"
                    transaction = Transaction(
                        project_id=project.id,
                        type="expense",
                        category_id=cat.id,
                        amount=amount,
                        currency="RUB",
                        description=desc,
                        date=t_date,
                    )
                    db.session.add(transaction)

                current = next_month

        db.session.commit()
        print("✅ Транзакции созданы")
        print("🎉 База данных успешно заполнена!")
        print("Логин: admin пароль: admin")
        print("Логин: user пароль: user")


if __name__ == "__main__":
    seed()
