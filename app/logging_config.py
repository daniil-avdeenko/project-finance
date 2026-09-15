import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(app):
    """Настраивает логирование в файл и консоль."""
    # Создаём папку для логов, если её нет
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Формат сообщений
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s в %(module)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1. Файловый обработчик с ротацией (10 МБ, 5 файлов максимум)
    file_handler = RotatingFileHandler(
        "logs/app.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # 2. Обработчик для консоли
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    # Настройка корневого логгера приложения
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.INFO)

    app.logger.info("Логирование запущено")
