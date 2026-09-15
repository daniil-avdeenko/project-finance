import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(app):
    """Настраивает логирование в файл и консоль для приложения и модулей."""
    # Создаём папку для логов
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    # Единый формат для всех handler'ов
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s в %(module)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Файловый handler с ротацией
    file_handler = RotatingFileHandler(
        "logs/app.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # Консольный handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    # Логгер "app" — родитель для всех модулей app.*
    # (app.integrations.grist_httpx, app.routes.projects ...)
    app_logger = logging.getLogger("app")
    app_logger.handlers.clear()  # убираем возможные дубли
    app_logger.addHandler(file_handler)
    app_logger.addHandler(console_handler)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False  # не пробрасывать в root logger

    # Flask-логгер — отдельный, для app.logger.info(...) внутри create_app
    app.logger.handlers.clear()
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = False

    app.logger.info("Логирование запущено")
