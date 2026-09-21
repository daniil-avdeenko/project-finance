from datetime import UTC, datetime

from flask_login import UserMixin
from sqlalchemy import event
from werkzeug.security import check_password_hash, generate_password_hash

from app import db


class EmployeeProject(db.Model):
    """
    Связь сотрудник-проект с ролью на проекте.

    Association Object вместо M2M: у связи есть поле `role`, которое
    описывает, кем сотрудник работает на конкретном проекте.
    """

    __tablename__ = "employee_projects"

    employee_id = db.Column(
        db.Integer, db.ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True
    )
    project_id = db.Column(
        db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    role = db.Column(db.String(100), nullable=False)

    employee = db.relationship("Employee", back_populates="project_roles")
    project = db.relationship("Project", back_populates="employee_roles")

    def __repr__(self) -> str:
        return f"<EmployeeProject emp={self.employee_id} proj={self.project_id} role={self.role}>"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="user")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == "admin"


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    is_deleted = db.Column(
        db.Boolean,
        default=False,
        server_default=db.text("0"),
        nullable=False,
        index=True,
    )
    created_at = db.Column(db.DateTime, default=datetime.now(UTC))

    employee_roles = db.relationship(
        "EmployeeProject",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def employees(self) -> list:
        """Список сотрудников проекта (без ролей). Для обратной совместимости."""
        return [er.employee for er in self.employee_roles]

    transactions = db.relationship(
        "Transaction",
        backref="project",
        lazy="dynamic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def total_income(self) -> float:
        """Сумма доходов в рублях (без удалённых транзакций)."""
        return sum(
            t.amount_rub
            for t in self.transactions.filter_by(is_deleted=False)
            if t.type == "income"
        )

    @property
    def total_expense(self) -> float:
        """Сумма расходов в рублях (без удалённых транзакций)."""
        return sum(
            t.amount_rub
            for t in self.transactions.filter_by(is_deleted=False)
            if t.type == "expense"
        )

    @property
    def profit(self) -> float:
        return round(self.total_income - self.total_expense, 2)

    @property
    def profitability(self):
        if self.total_income == 0:
            return 0
        return round((self.profit / self.total_income) * 100, 2)

    @classmethod
    def active(cls):
        """Активные проекты (не удалённые)."""
        return cls.query.filter_by(is_deleted=False)

    def __repr__(self):
        return f"<Project {self.name}>"


class Employee(db.Model):
    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))

    project_roles = db.relationship(
        "EmployeeProject",
        back_populates="employee",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def projects(self) -> list:
        """Список проектов сотрудника. Для обратной совместимости."""
        return [er.project for er in self.project_roles]

    @property
    def roles(self) -> list[str]:
        """Уникальные роли сотрудника по всем проектам."""
        seen = []
        for er in self.project_roles:
            if er.role and er.role not in seen:
                seen.append(er.role)
        return seen

    def __repr__(self):
        return f"<Employee {self.name}>"


class IncomeCategory(db.Model):
    __tablename__ = "income_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_default = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<IncomeCategory {self.name}>"


class ExpenseCategory(db.Model):
    __tablename__ = "expense_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_default = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<ExpenseCategory {self.name}>"


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    type = db.Column(db.String(10), nullable=False)  # 'income' или 'expense'
    category_id = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default="RUB")
    description = db.Column(db.String(255))
    is_deleted = db.Column(
        db.Boolean,
        default=False,
        server_default=db.text("0"),
        nullable=False,
        index=True,
    )
    date = db.Column(db.DateTime, default=datetime.now(UTC))

    @classmethod
    def active(cls):
        """Активные транзакции (не удалённые)."""
        return cls.query.filter_by(is_deleted=False)

    def __repr__(self):
        return f"<Transaction {self.type} {self.amount} {self.currency}>"

    @property
    def amount_rub(self) -> float:
        """
        Сумма в рублях по курсу ЦБ на дату транзакции.
        """
        from app.services.currency_service import convert_to_rub

        tx_date = self.date.date() if self.date else None
        return convert_to_rub(self.amount, self.currency or "RUB", tx_date)


class EventLog(db.Model):
    """
    Очередь событий для event-driven уведомлений.

    Записи создаются автоматически при INSERT Project/Transaction,
    а scheduler раз в 30 секунд собирает pending и отправляет их в Telegram.
    """

    __tablename__ = "event_log"

    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(50), nullable=False, index=True)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    sent_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (db.Index("ix_event_log_status_created", "status", "created_at"),)

    def __repr__(self) -> str:
        return f"<EventLog {self.event_type} status={self.status}>"


class CurrencyRate(db.Model):
    """
    Курс валюты ЦБ РФ на конкретную дату.

    code — буквенный код (USD, EUR, ...).
    nominal — за сколько единиц указан курс (обычно 1, но JPY — 100, VND — 10000).
    rate_rub — курс в рублях за nominal единиц.

    Уникальность (code, rate_date) — на одну дату один курс.
    Используется для конвертации транзакций в рубли.
    """

    __tablename__ = "currency_rates"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), nullable=False, index=True)
    rate_date = db.Column(db.Date, nullable=False, index=True)
    nominal = db.Column(db.Integer, nullable=False, default=1)
    rate_rub = db.Column(db.Float, nullable=False)

    __table_args__ = (db.UniqueConstraint("code", "rate_date", name="uq_currency_rate_code_date"),)

    def __repr__(self) -> str:
        return f"<CurrencyRate {self.code} {self.rate_date}={self.rate_rub}>"


# ============================================================
#   Каскадный soft delete
# ============================================================


@event.listens_for(Project, "after_update")
def _cascade_soft_delete_transactions(mapper, connection, target):
    """
    При soft delete проекта помечает его транзакции удалёнными.

    Использует low-level connection, а не db.session — listener
    работает внутри транзакции update, сессия недоступна.

    Работает независимо от того, откуда вызвано удаление:
    роут, CLI, seed, миграция.
    """
    if not target.is_deleted:
        return

    connection.execute(
        Transaction.__table__.update()
        .where(Transaction.__table__.c.project_id == target.id)
        .where(Transaction.__table__.c.is_deleted == False)  # noqa: E712
        .values(is_deleted=True)
    )
