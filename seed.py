"""
Наполнение БД тестовыми данными.

Схема: 6 проектов (4 отечественных + 2 зарубежных), 30 сотрудников
с ролями на проектах, исторические курсы USD/EUR за 12 месяцев,
транзакции за период существования проектов.

Реалистичная модель данных:
- Доходы отечественных проектов — RUB, зарубежных — EUR/USD.
- Расходы в основном RUB (ЗП, налоги, юр. услуги, аренда сервера).
- Валютные расходы (командировки, внешние программисты, ИИ, маркетинг) —
  только у зарубежных проектов.
- Налоги — всегда RUB, ~13% от месячного ФОТ.
- Внешние разработчики — только внешние, работают на 3–4 проектах.
- Менеджеры и тимлиды курируют несколько проектов, но не пересекаются
  с ролями разработки.
- Если у сотрудника есть роли «Разработчик» и «Старший разработчик»,
  старший — на отечественном проекте, обычный — на зарубежном
  (зарубежные проекты сложнее, роль «даунгрейдится»).

Флаг EVENTS_ENABLED=false отключает event_log — иначе на ~400 транзакций
прилетит столько же событий, и scheduler завалит Telegram.

Запуск:
    python seed.py
"""

import os
import random
from datetime import UTC, datetime, timedelta

from app import create_app, db
from app.models import (
    CurrencyRate,
    Employee,
    EmployeeProject,
    ExpenseCategory,
    IncomeCategory,
    Project,
    Transaction,
    User,
)

# ============================================================
#   КОНСТАНТЫ
# ============================================================

APPROX_RATES = {"USD": 84.0, "EUR": 97.0}

# Доходные категории, доступные для зарубежных проектов
INTL_INCOME_CATS = {
    "Разработка ПО на заказ",
    "Продажа готового ПО",
    "Интеграционные услуги",
    "Техническая поддержка",
    "Консультационные услуги",
}

# Расходные категории, которые могут быть в валюте (для зарубежных проектов).
# Остальные — только RUB: ЗП российских сотрудников, налоги, юр. услуги, аренда.
INTL_EXPENSE_CATS = {
    "Внешние программисты",
    "Расходы на ИИ",
    "Маркетинг",
    "Командировки",
}


# ============================================================
#   ПРОЕКТЫ
# ============================================================

# target_income_month / target_expense_month всегда в RUB.
# Для зарубежных проектов указан рублёвый эквивалент суммы в валюте.
PROJECT_DEFS = [
    {
        "name": "CRM для банка «Альфа»",
        "description": (
            "Разработка и внедрение CRM-системы для банка. " "Интеграция с телефонией и чат-ботами."
        ),
        "currency": "RUB",
        "income_cats": ["Разработка ПО на заказ", "Консультационные услуги"],
        "expense_cats": [
            "Внутренние программисты",
            "Внешние программисты",
            "Аренда сервера",
            "Расходы на ИИ",
            "Маркетинг",
            "Налоги и сборы",
        ],
        "target_income_month": 5_300_000,
        "target_expense_month": 3_700_000,
        "months_ago": 9,
    },
    {
        "name": "Интеграция 1С для сети «Бета»",
        "description": ("Настройка обмена данными между 1С:Управление торговлей и Битрикс24."),
        "currency": "RUB",
        "income_cats": ["Интеграционные услуги", "Консультационные услуги"],
        "expense_cats": [
            "Внутренние программисты",
            "Внешние программисты",
            "Командировки",
            "Юридические услуги",
            "Налоги и сборы",
        ],
        "target_income_month": 2_600_000,
        "target_expense_month": 1_900_000,
        "months_ago": 5,
    },
    {
        "name": "Мобильное приложение для доставки «Гамма»",
        "description": ("Разработка мобильного приложения для заказа еды с интеграцией в CRM."),
        "currency": "RUB",
        "income_cats": ["Разработка ПО на заказ"],
        "expense_cats": [
            "Внутренние программисты",
            "Расходы на ИИ",
            "Маркетинг",
            "Налоги и сборы",
        ],
        "target_income_month": 2_800_000,
        "target_expense_month": 2_000_000,
        "months_ago": 7,
    },
    {
        "name": "Облачная платформа IoT для «Дельта»",
        "description": ("Создание облачной платформы для управления IoT-устройствами."),
        "currency": "RUB",
        "income_cats": ["Продажа готового ПО", "Абонентское обслуживание"],
        "expense_cats": [
            "Внутренние программисты",
            "Аренда сервера",
            "Расходы на ИИ",
            "Налоги и сборы",
        ],
        "target_income_month": 3_800_000,
        "target_expense_month": 2_750_000,
        "months_ago": 8,
    },
    {
        "name": "Schmidt Logistics (Германия)",
        "description": (
            "Разработка REST API и интеграционных модулей " "для логистической платформы клиента."
        ),
        "currency": "EUR",
        "income_cats": [
            "Разработка ПО на заказ",
            "Интеграционные услуги",
            "Техническая поддержка",
        ],
        "expense_cats": [
            "Внутренние программисты",
            "Внешние программисты",
            "Расходы на ИИ",
            "Маркетинг",
            "Командировки",
            "Налоги и сборы",
        ],
        # ≈ 30 000 EUR/мес × 97
        "target_income_month": 2_910_000,
        # ≈ 21 000 EUR/мес × 97
        "target_expense_month": 2_040_000,
        "months_ago": 6,
    },
    {
        "name": "Bright Path Inc. (США)",
        "description": (
            "SaaS-платформа для управления распределёнными командами. "
            "Долгосрочный контракт на разработку и поддержку."
        ),
        "currency": "USD",
        "income_cats": [
            "Разработка ПО на заказ",
            "Продажа готового ПО",
            "Консультационные услуги",
        ],
        "expense_cats": [
            "Внутренние программисты",
            "Внешние программисты",
            "Расходы на ИИ",
            "Командировки",
            "Налоги и сборы",
        ],
        # ≈ 35 000 USD/мес × 84
        "target_income_month": 2_940_000,
        # ≈ 24 000 USD/мес × 84
        "target_expense_month": 2_020_000,
        "months_ago": 5,
    },
]


# ============================================================
#   СОТРУДНИКИ И РОЛИ
# ============================================================

# Индексы проектов:
# 0 = CRM для банка «Альфа»
# 1 = Интеграция 1С для сети «Бета»
# 2 = Мобильное приложение «Гамма»
# 3 = Облачная платформа IoT «Дельта»
# 4 = Schmidt Logistics (EUR)
# 5 = Bright Path Inc. (USD)
#
# Сотрудники с 2+ ролями на разных проектах:
#   Петрова, Сидоров, Смирнова, Кузнецов, Попова, Лебедев, Волкова,
#   Громов, Медведева, Белов — всего 10 человек.
# Внешние разработчики (4 человека) — только «Внешний разработчик»,
# зато на 3–4 проектах каждый.

EMPLOYEES: list[tuple[str, list[tuple[int, str]]]] = [
    # --- Тимлиды (3) ---
    (
        "Иванов Иван Иванович",
        [
            (0, "Тимлид"),
            (1, "Тимлид"),
        ],
    ),
    (
        "Козлов Владимир Олегович",
        [
            (2, "Тимлид"),
            (3, "Тимлид"),
        ],
    ),
    (
        "Новикова Ирина Евгеньевна",
        [
            (4, "Тимлид"),
            (5, "Тимлид"),
        ],
    ),
    # --- Менеджеры проектов (2) ---
    (
        "Орлов Виктор Сергеевич",
        [
            (0, "Менеджер проектов"),
            (2, "Менеджер проектов"),
            (4, "Менеджер проектов"),
        ],
    ),
    (
        "Титов Павел Андреевич",
        [
            (1, "Менеджер проектов"),
            (3, "Менеджер проектов"),
            (5, "Менеджер проектов"),
        ],
    ),
    # --- DevOps-инженеры (2) ---
    (
        "Алексеева Наталья Анатольевна",
        [
            (0, "DevOps-инженер"),
            (2, "DevOps-инженер"),
            (4, "DevOps-инженер"),
        ],
    ),
    (
        "Васильев Олег Дмитриевич",
        [
            (1, "DevOps-инженер"),
            (3, "DevOps-инженер"),
            (5, "DevOps-инженер"),
        ],
    ),
    # --- Аналитики (4) ---
    (
        "Громов Станислав Юрьевич",
        [
            (0, "Аналитик"),
            (4, "Консультант"),
        ],
    ),
    (
        "Фёдорова Екатерина Максимовна",
        [
            (1, "Аналитик"),
            (5, "Аналитик"),
        ],
    ),
    (
        "Михайлов Денис Валерьевич",
        [
            (2, "Аналитик"),
            (3, "Аналитик"),
        ],
    ),
    (
        "Медведева Галина Игоревна",
        [
            (4, "Аналитик"),
            (5, "Консультант"),
        ],
    ),
    # --- Старшие разработчики (5) ---
    (
        "Петрова Анна Сергеевна",
        [
            (0, "Старший разработчик"),
            (2, "Старший разработчик"),
            (4, "Аналитик"),
        ],
    ),
    (
        "Сидоров Сергей Сергеевич",
        [
            (1, "Старший разработчик"),
            (3, "Тимлид"),
        ],
    ),
    (
        "Смирнова Елена Дмитриевна",
        [
            (2, "Старший разработчик"),
            (4, "Консультант"),
        ],
    ),
    (
        "Кузнецов Андрей Николаевич",
        [
            (3, "Старший разработчик"),
            (5, "Консультант"),
        ],
    ),
    (
        "Волкова Татьяна Романовна",
        [
            (0, "Разработчик"),
            (1, "Старший разработчик"),
        ],
    ),
    # --- Разработчики (5) ---
    # Правило: если у сотрудника есть роли «Разработчик» и «Старший разработчик»,
    # то старший — на отечественном проекте, обычный — на зарубежном
    (
        "Попова Мария Александровна",
        [
            (0, "Старший разработчик"),
            (4, "Разработчик"),
        ],
    ),
    (
        "Лебедев Максим Игоревич",
        [
            (1, "Старший разработчик"),
            (5, "Разработчик"),
        ],
    ),
    (
        "Соколова Ольга Викторовна",
        [
            (2, "Разработчик"),
            (5, "Разработчик"),
        ],
    ),
    (
        "Морозов Никита Павлович",
        [
            (3, "Разработчик"),
        ],
    ),
    # --- Тестировщики (2) ---
    (
        "Андреева Светлана Николаевна",
        [
            (0, "Тестировщик"),
            (2, "Тестировщик"),
            (4, "Тестировщик"),
        ],
    ),
    (
        "Фомин Григорий Семёнович",
        [
            (1, "Тестировщик"),
            (3, "Тестировщик"),
            (5, "Тестировщик"),
        ],
    ),
    # --- Инженеры поддержки и консультанты (4) ---
    (
        "Борисова Ксения Артёмовна",
        [
            (0, "Инженер поддержки"),
            (1, "Инженер поддержки"),
        ],
    ),
    (
        "Белов Юрий Владимирович",
        [
            (2, "Инженер поддержки"),
            (4, "Консультант"),
        ],
    ),
    (
        "Гаврилов Константин Петрович",
        [
            (0, "Консультант"),
            (3, "Консультант"),
        ],
    ),
    (
        "Тихонов Игорь Сергеевич",
        [
            (1, "Консультант"),
            (5, "Консультант"),
        ],
    ),
    # --- Внешние разработчики (4) — на 3–4 проектах ---
    (
        "Шмидт Андрей Викторович",
        [
            (0, "Внешний разработчик"),
            (2, "Внешний разработчик"),
            (4, "Внешний разработчик"),
            (5, "Внешний разработчик"),
        ],
    ),
    (
        "Мюллер Елена Александровна",
        [
            (1, "Внешний разработчик"),
            (3, "Внешний разработчик"),
            (5, "Внешний разработчик"),
        ],
    ),
    (
        "Фишер Павел Дмитриевич",
        [
            (0, "Внешний разработчик"),
            (1, "Внешний разработчик"),
            (2, "Внешний разработчик"),
            (4, "Внешний разработчик"),
        ],
    ),
    (
        "Вебер Ольга Сергеевна",
        [
            (3, "Внешний разработчик"),
            (4, "Внешний разработчик"),
            (5, "Внешний разработчик"),
        ],
    ),
]


# ============================================================
#   ХЕЛПЕРЫ
# ============================================================


def _make_email(name: str, external: bool = False) -> str:
    """Строит email из ФИО: имя.фамилия@domain."""
    prefix = name.lower().replace(" ", ".")
    domain = "@external.com" if external else "@company.ru"
    return prefix + domain


def _make_phone() -> str:
    """Реалистичный российский мобильный номер."""
    return (
        f"+7 999 {random.randint(100, 999)}-" f"{random.randint(10, 99)}-{random.randint(10, 99)}"
    )


def _pick_income_currency(project_currency: str) -> str:
    """Отечественные — RUB, зарубежные — валюта проекта."""
    return project_currency


def _pick_expense_currency(category: str, project_currency: str) -> str:
    """
    Валюта расхода по категории.

    Отечественные проекты — всегда RUB.
    Зарубежные — валюта проекта для INTL_EXPENSE_CATS, остальное RUB.
    """
    if project_currency == "RUB":
        return "RUB"
    if category in INTL_EXPENSE_CATS:
        return project_currency
    return "RUB"


def _amount_in_currency(rub_amount: float, currency: str) -> float:
    """Конвертирует рублёвую сумму в валюту по приблизительному курсу."""
    if currency == "RUB":
        return round(rub_amount, 2)
    return round(rub_amount / APPROX_RATES[currency], 2)


def _is_external(roles: list[tuple[int, str]]) -> bool:
    """True, если сотрудник — внешний разработчик (все роли такие)."""
    return all(role == "Внешний разработчик" for _, role in roles)


# ============================================================
#   SEED
# ============================================================


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
        expense_names = [
            "Внутренние программисты",
            "Внешние программисты",
            "Расходы на ИИ",
            "Аренда сервера",
            "Маркетинг",
            "Командировки",
            "Юридические услуги",
            "Налоги и сборы",
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
        now = datetime.now(UTC)
        projects = []
        for p_def in PROJECT_DEFS:
            start = now - timedelta(days=p_def["months_ago"] * 30)
            p = Project(
                name=p_def["name"],
                description=p_def["description"],
                created_at=start,
            )
            db.session.add(p)
            projects.append(p)
        db.session.commit()
        print(f"✅ {len(projects)} проектов создано")

        # ---------- 4. СОТРУДНИКИ ----------
        employees_by_name: dict[str, Employee] = {}
        for name, roles in EMPLOYEES:
            external = _is_external(roles)
            emp = Employee(
                name=name,
                phone=_make_phone(),
                email=_make_email(name, external=external),
            )
            db.session.add(emp)
            employees_by_name[name] = emp
        db.session.commit()
        print(f"✅ {len(employees_by_name)} сотрудников создано")

        # ---------- 5. ПРИВЯЗКИ СОТРУДНИКОВ К ПРОЕКТАМ ----------
        total_links = 0
        for name, roles in EMPLOYEES:
            emp = employees_by_name[name]
            for project_idx, role in roles:
                db.session.add(
                    EmployeeProject(
                        employee_id=emp.id,
                        project_id=projects[project_idx].id,
                        role=role,
                    )
                )
                total_links += 1
        db.session.commit()
        print(f"✅ Привязок сотрудник-проект создано: {total_links}")

        # ---------- 6. КУРСЫ ВАЛЮТ ----------
        CurrencyRate.query.delete()
        db.session.commit()

        base_rate = {"USD": 84.0, "EUR": 97.0}
        months_back_max = 12

        for months_back in range(months_back_max + 1):
            rate_date = (now - timedelta(days=months_back * 30)).date()
            for code, base in base_rate.items():
                drift = random.uniform(-3.0, 3.0)
                db.session.add(
                    CurrencyRate(
                        code=code,
                        rate_date=rate_date,
                        nominal=1,
                        rate_rub=round(base + drift, 4),
                    )
                )

        db.session.commit()
        print(f"✅ Курсы валют созданы " f"({len(base_rate) * (months_back_max + 1)} записей)")

        # ---------- 7. ТРАНЗАКЦИИ ----------
        for proj_idx, project in enumerate(projects):
            p_def = PROJECT_DEFS[proj_idx]
            project_currency = p_def["currency"]
            start_date = project.created_at.replace(tzinfo=UTC)
            end_date = now

            current = start_date
            while current < end_date:
                next_month = current.replace(day=28) + timedelta(days=4)
                next_month = next_month.replace(day=1)

                target_income_rub = p_def["target_income_month"]
                target_expense_rub = p_def["target_expense_month"]

                # --- ДОХОДЫ ---
                num_income = random.randint(3, 5)
                income_cats_for_proj = [income_cats[name] for name in p_def["income_cats"]]
                for _ in range(num_income):
                    cat = random.choice(income_cats_for_proj)
                    rub_amount = round(
                        target_income_rub / num_income * random.uniform(0.7, 1.3),
                        2,
                    )
                    currency = _pick_income_currency(project_currency)
                    amount = _amount_in_currency(rub_amount, currency)

                    day = random.randint(1, 28)
                    t_date = current.replace(day=min(day, 28)) + timedelta(
                        days=random.randint(0, 2)
                    )
                    t_date = t_date.replace(
                        hour=random.randint(9, 17),
                        minute=random.choice([0, 30]),
                    )
                    if t_date > end_date:
                        t_date = end_date - timedelta(days=1)

                    db.session.add(
                        Transaction(
                            project_id=project.id,
                            type="income",
                            category_id=cat.id,
                            amount=amount,
                            currency=currency,
                            description=f"Поступление по {cat.name}",
                            date=t_date,
                        )
                    )

                # --- РАСХОДЫ (без налогов) ---
                # Налоги считаем отдельно как 13% от ФОТ. Упрощение: ФОТ = 50%
                # расходов (реалистично для IT-проекта).
                payroll_target_rub = target_expense_rub * 0.5
                tax_rub = round(payroll_target_rub * 0.13, 2)

                expense_cats_no_tax = [
                    name for name in p_def["expense_cats"] if name != "Налоги и сборы"
                ]

                num_expense = random.randint(4, 6)
                expense_cats_for_proj = [expense_cats[name] for name in expense_cats_no_tax]
                for _ in range(num_expense):
                    cat = random.choice(expense_cats_for_proj)
                    rub_amount = round(
                        target_expense_rub / num_expense * random.uniform(0.7, 1.3),
                        2,
                    )
                    currency = _pick_expense_currency(cat.name, project_currency)
                    amount = _amount_in_currency(rub_amount, currency)

                    day = random.randint(1, 28)
                    t_date = current.replace(day=min(day, 28)) + timedelta(
                        days=random.randint(0, 2)
                    )
                    t_date = t_date.replace(
                        hour=random.randint(9, 17),
                        minute=random.choice([0, 30]),
                    )
                    if t_date > end_date:
                        t_date = end_date - timedelta(days=1)

                    db.session.add(
                        Transaction(
                            project_id=project.id,
                            type="expense",
                            category_id=cat.id,
                            amount=amount,
                            currency=currency,
                            description=f"Оплата по {cat.name}",
                            date=t_date,
                        )
                    )

                # --- НАЛОГИ: всегда RUB, ~13% от ФОТ ---
                if "Налоги и сборы" in p_def["expense_cats"]:
                    tax_cat = expense_cats["Налоги и сборы"]
                    t_date = current.replace(day=28, hour=18, minute=0)
                    if t_date > end_date:
                        t_date = end_date - timedelta(days=1)

                    db.session.add(
                        Transaction(
                            project_id=project.id,
                            type="expense",
                            category_id=tax_cat.id,
                            amount=tax_rub,
                            currency="RUB",
                            description="Налоги и сборы за месяц",
                            date=t_date,
                        )
                    )

                current = next_month

        db.session.commit()
        print("✅ Транзакции созданы")
        print("🎉 База данных успешно заполнена!")
        print("Логин: admin пароль: admin")
        print("Логин: user пароль: user")


if __name__ == "__main__":
    seed()
