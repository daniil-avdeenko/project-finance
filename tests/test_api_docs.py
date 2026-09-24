"""Тесты документации API."""


def test_openapi_json_returns_valid_spec(client):
    """GET /api/v1/openapi.json возвращает OpenAPI 3.x."""
    response = client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    spec = response.get_json()
    assert spec["openapi"].startswith("3.")
    assert "paths" in spec
    assert "/api/v1/health" in spec["paths"]


def test_docs_page_renders_swagger_ui(client):
    """GET /api/v1/docs отдаёт HTML со swagger-ui."""
    response = client.get("/api/v1/docs")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "swagger-ui" in html.lower()
