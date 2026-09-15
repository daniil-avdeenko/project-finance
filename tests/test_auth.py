from app import db as _db
from app.models import User


def test_login_success(app):
    """Успешный вход с правильными данными перенаправляет на главную."""
    with app.app_context():
        user = User(username='test_user', role='user')
        user.set_password('correct_password')
        _db.session.add(user)
        _db.session.commit()

    client = app.test_client()
    response = client.post('/login', data={
        'username': 'test_user',
        'password': 'correct_password'
    }, follow_redirects=False)

    assert response.status_code == 302
    assert response.location == '/' or response.location.endswith('/')


def test_login_wrong_password(app):
    """Неверный пароль — редирект обратно на /login."""
    with app.app_context():
        user = User(username='test_user', role='user')
        user.set_password('correct_password')
        _db.session.add(user)
        _db.session.commit()

    client = app.test_client()
    response = client.post('/login', data={
        'username': 'test_user',
        'password': 'wrong_password'
    }, follow_redirects=False)

    assert response.status_code == 302
    assert '/login' in response.location


def test_login_unknown_user(app):
    """Несуществующий пользователь — редирект обратно на /login."""
    client = app.test_client()
    response = client.post('/login', data={
        'username': 'no_such_user',
        'password': 'any_password'
    }, follow_redirects=False)

    assert response.status_code == 302
    assert '/login' in response.location


def test_logout(auth_client):
    """Выход из системы перенаправляет на /login."""
    response = auth_client.get('/logout', follow_redirects=False)

    assert response.status_code == 302
    assert '/login' in response.location


def test_login_when_already_authorized(auth_client):
    """Если уже вошёл — GET /login перенаправляет на главную."""
    response = auth_client.get('/login', follow_redirects=False)

    assert response.status_code == 302
    assert response.location == '/' or response.location.endswith('/')


def test_admin_can_access_create_project(auth_client):
    """Админ может зайти на /projects/create."""
    response = auth_client.get('/projects/create')
    assert response.status_code == 200


def test_user_role_cannot_access_create_project(regular_client):
    """Пользователь с ролью 'user' не может зайти на /projects/create."""
    response = regular_client.get('/projects/create', follow_redirects=False)
    assert response.status_code == 302
    assert response.location == '/' or response.location.endswith('/')


def test_admin_can_access_create_employee(auth_client):
    """Админ может зайти на /employees/create."""
    response = auth_client.get('/employees/create')
    assert response.status_code == 200


def test_user_role_cannot_access_create_employee(regular_client):
    """Пользователь с ролью 'user' не может зайти на /employees/create."""
    response = regular_client.get('/employees/create', follow_redirects=False)
    assert response.status_code == 302
    assert response.location == '/' or response.location.endswith('/')


def test_user_role_cannot_access_create_category(regular_client):
    """Пользователь с ролью 'user' не может создавать категории."""
    response = regular_client.get('/income-categories/create', follow_redirects=False)
    assert response.status_code == 302
    assert response.location == '/' or response.location.endswith('/')


def test_admin_can_access_create_category(auth_client):
    """Админ может зайти на /income-categories/create."""
    response = auth_client.get('/income-categories/create')
    assert response.status_code == 200