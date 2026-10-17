"""Тесты документации API: спека, роуты, UI."""


def test_openapi_json_requires_login(client):
    """Без логина /openapi.json недоступен."""
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 302
    assert "/login" in response.location


def test_docs_requires_login(client):
    response = client.get("/api/v1/docs")
    assert response.status_code == 302


def test_redoc_requires_login(client):
    response = client.get("/api/v1/redoc")
    assert response.status_code == 302


def test_openapi_json_returns_valid_spec(auth_client):
    """Залогиненный видит OpenAPI 3.x."""
    response = auth_client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    spec = response.get_json()
    assert spec["openapi"].startswith("3.")
    assert "paths" in spec


def test_openapi_spec_covers_all_api_routes(auth_client, app):
    """
    Каждый не-docs роут /api/v1/* должен быть описан в спеке.

    Защищает от рассинхрона: добавил эндпоинт — не забыл описать.
    Docs-роуты сами себя не описывают, они исключены.

    Нормализация: Flask хранит пути как /projects/<int:id>,
    OpenAPI — как /projects/{id}. Приводим к одному виду.
    """
    import re

    from app.api.v1.openapi_spec import build_openapi_spec

    def _normalize(path: str) -> str:
        # <int:project_id> → {project_id}, <project_id> → {project_id}
        # (?:...)? — опциональная группа «тип:», (\w+) — имя параметра
        return re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", path)

    spec = build_openapi_spec()
    spec_paths = {_normalize(p) for p in spec["paths"]}

    excluded = {
        "/api/v1/docs",
        "/api/v1/redoc",
        "/api/v1/openapi.json",
    }

    real_paths = set()
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/v1/") and rule.rule not in excluded:
            real_paths.add(_normalize(rule.rule))

    missing = real_paths - spec_paths
    assert not missing, f"Роуты отсутствуют в OpenAPI-спеке: {missing}"


def test_docs_page_renders_swagger_ui(auth_client):
    response = auth_client.get("/api/v1/docs")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "swagger-ui" in html.lower()
    assert "5.17.14" in html  # версия запинена


def test_redoc_page_renders(auth_client):
    response = auth_client.get("/api/v1/redoc")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "redoc" in html.lower()


def test_openapi_servers_url_respects_forwarded_proto(auth_client):
    """За прокси Swagger показывает https, а не http — иначе Try it out уйдёт в редирект-цикл."""
    response = auth_client.get(
        "/api/v1/openapi.json",
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "projectfin.com.ru",
        },
    )

    assert response.status_code == 200
    spec = response.get_json()
    assert spec["servers"][0]["url"] == "https://projectfin.com.ru"


def test_openapi_servers_url_defaults_to_http_locally(auth_client):
    """Без X-Forwarded-Proto — http://127.0.0.1, чтобы локально тоже работало."""
    response = auth_client.get("/api/v1/openapi.json")

    spec = response.get_json()
    assert spec["servers"][0]["url"].startswith("http://")
