from datetime import UTC, datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db

# Промежуточная таблица для связи многие-ко-многим (Employee <-> Project)
employee_projects = db.Table(
    "employee_projects",
    db.Column("employee_id", db.Integer, db.ForeignKey("employees.id"), primary_key=True),
    db.Column("project_id", db.Integer, db.ForeignKey("projects.id"), primary_key=True),
)


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
    created_at = db.Column(db.DateTime, default=datetime.now(UTC))

    # Связь с сотрудниками (many-to-many)
    employees = db.relationship("Employee", secondary=employee_projects, back_populates="projects")
    transactions = db.relationship(
        "Transaction",
        backref="project",
        lazy="dynamic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def total_income(self) -> float:
        return sum(t.amount_rub for t in self.transactions if t.type == "income")

    @property
    def total_expense(self) -> float:
        return sum(t.amount_rub for t in self.transactions if t.type == "expense")

    @property
    def profit(self) -> float:
        return round(self.total_income - self.total_expense, 2)

    @property
    def profitability(self):
        if self.total_income == 0:
            return 0
        return round((self.profit / self.total_income) * 100, 2)

    def __repr__(self):
        return f"<Project {self.name}>"


class Employee(db.Model):
    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))

    # Связь с проектами (many-to-many)
    projects = db.relationship("Project", secondary=employee_projects, back_populates="employees")

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
    date = db.Column(db.DateTime, default=datetime.now(UTC))

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
