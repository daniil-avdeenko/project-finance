import asyncio
import os
import sqlite3

from dotenv import load_dotenv
from flask import Flask, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import joinedload

from app.logging_config import setup_logging
from app.security import register_security_headers

load_dotenv()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://",
)
db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """
    Включаем поддержку внешних ключей в SQLite (для каскадного удаления).
    Выполняется ТОЛЬКО для SQLite-подключений — PostgreSQL не понимает PRAGMA.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)

    # Конфигурация
    flask_env = os.getenv("FLASK_ENV", "development")
    secret_key = os.getenv("SECRET_KEY")

    if not secret_key:
        if flask_env == "production":
            raise RuntimeError(
                "SECRET_KEY не установлен. В production это обязательно — "
                "иначе сессии можно подделать."
            )
        secret_key = "dev-key-for-testing"
        app.logger.warning("SECRET_KEY не установлен, используется dev-значение")

    app.config["SECRET_KEY"] = secret_key

    database_url = os.getenv("DATABASE_URL")

    if database_url:
        # Railway/Render могут отдавать postgres://
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)

        # Явно указываем драйвер psycopg (v3) для SQLAlchemy
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

        app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///project_finance.db"

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    setup_logging(app)
    register_security_headers(app)

    # Активируем event-driven listeners
    from app import (
        events,  # noqa: F401
        models,  # noqa: F401
    )

    # Инициализация расширений
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    app.config["RATELIMIT_ENABLED"] = os.getenv("RATELIMIT_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Пожалуйста, войдите для доступа."

    # Регистрация Blueprint'ов
    from app.routes import main_bp

    app.register_blueprint(main_bp)

    from app.routes.auth import auth_bp

    app.register_blueprint(auth_bp)

    # Глобальный фильтр для форматирования денег
    @app.template_filter("money")
    def money_filter(value):
        if value is None:
            return "0.00"
        try:
            formatted = f"{float(value):,.2f}".replace(",", " ")
            return formatted
        except (ValueError, TypeError):
            return str(value)

    # Обработчики ошибок
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(429)
    def ratelimit_handler(error):
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.error(f"Internal Server Error: {error}", exc_info=True)
        return render_template("errors/500.html"), 500

    @app.route("/healthz")
    def healthz():
        """
        Healthcheck для Railway/Docker.
        """

        return {"status": "ok"}, 200

    # команда для импорта в Grist
    @app.cli.command("sync-grist-httpx")
    def sync_grist_httpx_command():
        """Синхронизирует данные из БД в Grist с помощью httpx (upsert)."""
        from app.integrations.grist_httpx import (
            sync_projects_to_grist_httpx,
            sync_transactions_to_grist_httpx,
        )
        from app.models import Project, Transaction

        app.logger.info("Начинаю синхронизацию с Grist через httpx...")
        try:
            projects = Project.query.all()
            transactions = (
                Transaction.query.options(joinedload(Transaction.project))
                .order_by(Transaction.date.desc())
                .all()
            )

            # Запускаем асинхронные задачи
            asyncio.run(sync_projects_to_grist_httpx(projects))
            asyncio.run(sync_transactions_to_grist_httpx(transactions))

            app.logger.info("Синхронизация с Grist через httpx успешно завершена.")
        except Exception as e:
            app.logger.error(f"Ошибка синхронизации с Grist: {e}", exc_info=True)

    # команда для проверки уведомлений Telegram
    @app.cli.command("send-test-message")
    def send_test_message_command():
        """Отправляет тестовое сообщение в Telegram для проверки настроек."""
        from app.integrations.telegram import send_message

        text = (
            "🧪 <b>Тестовое сообщение</b>\n\n"
            "Telegram-интеграция работает.\n"
            "Проект: project-finance"
        )

        ok = asyncio.run(send_message(text))
        if ok:
            app.logger.info("Тестовое сообщение отправлено")
        else:
            app.logger.error("Не удалось отправить тестовое сообщение")

    @app.cli.command("scrape-cbr")
    def scrape_cbr_command():
        """Парсит курсы ЦБ через Playwright и сохраняет в БД + Grist."""
        import asyncio

        from app.integrations.cbr_scraper import scrape_cbr_rates
        from app.integrations.grist_httpx import sync_rates_to_grist_httpx
        from app.services.currency_service import upsert_rates

        app.logger.info("Начинаю парсинг курсов ЦБ...")
        try:
            rates = asyncio.run(scrape_cbr_rates())
            if not rates:
                app.logger.warning("Курсы не получены")
                return

            app.logger.info("Получено %d курсов", len(rates))

            # 1. БД — источник истины для расчётов
            db_result = upsert_rates(rates)
            app.logger.info(
                "БД: добавлено %d, обновлено %d",
                db_result["added"],
                db_result["updated"],
            )

            # 2. Grist — витрина для команды
            result = asyncio.run(sync_rates_to_grist_httpx(rates))
            app.logger.info(
                "Grist: добавлено %d, обновлено %d",
                result.get("added", 0),
                result.get("updated", 0),
            )
        except Exception as e:
            app.logger.error("Ошибка scrape-cbr: %s", e, exc_info=True)

    @app.cli.command("sync-sheets")
    def sync_sheets_command():
        """Синхронизирует проекты и транзакции в Google Sheets."""
        from app.integrations.google_sheets import sync_all_to_sheets
        from app.models import Project, Transaction

        app.logger.info("Начинаю синхронизацию с Google Sheets...")
        try:
            projects = Project.query.all()
            transactions = (
                Transaction.query.options(joinedload(Transaction.project))
                .order_by(Transaction.date.desc())
                .all()
            )
            result = sync_all_to_sheets(projects, transactions)
            app.logger.info(
                "Google Sheets: %d проектов, %d транзакций",
                result["projects"],
                result["transactions"],
            )
        except Exception as e:
            app.logger.error("Ошибка sync-sheets: %s", e, exc_info=True)

    return app


# Загрузчик пользователя для Flask-Login
@login_manager.user_loader
def load_user(user_id):
    from app.models import User

    return db.session.get(User, int(user_id))
