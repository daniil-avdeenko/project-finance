import os
import sys

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Переопределяем переменные окружения ДО импорта приложения
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-key"
os.environ["RATELIMIT_ENABLED"] = "false"

import pytest

from app import create_app
from app import db as _db
from app.models import User


@pytest.fixture
def app():
    """Создаёт приложение с тестовой конфигурацией."""
    app = create_app()
    app.config.update(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
        }
    )

    # Отключаем логирование в тестах
    import logging

    app.logger.setLevel(logging.CRITICAL)
    app.logger.handlers.clear()

    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()
        _db.engine.dispose()


@pytest.fixture
def client(app):
    """Тестовый клиент для отправки HTTP-запросов."""
    return app.test_client()


@pytest.fixture
def admin_user(app):
    """Создаёт администратора."""
    admin = User(username="admin", role="admin")
    admin.set_password("admin")
    _db.session.add(admin)
    _db.session.commit()
    return admin


@pytest.fixture
def auth_client(client, admin_user):
    """Клиент с авторизованным админом."""
    with client.session_transaction() as session:
        session["_user_id"] = str(admin_user.id)
        session["_fresh"] = True
    return client


@pytest.fixture
def regular_client(app):
    """Клиент с авторизованным обычным пользователем (role='user')."""
    with app.app_context():
        user = User(username="regular_user", role="user")
        user.set_password("user_pass")
        _db.session.add(user)
        _db.session.commit()
        user_id = user.id

    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True
    return client
