"""Тесты публичного API: healthcheck и JSON-ошибки."""


def test_api_health_returns_ok(client):
    """GET /api/v1/health возвращает 200 и JSON без авторизации."""
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "project-finance-api"
    assert data["version"] == "v1"


def test_api_404_returns_json(client):
    """Несуществующий API-эндпоинт → JSON, не HTML."""
    response = client.get("/api/v1/nonexistent")

    assert response.status_code == 404
    data = response.get_json()
    assert data["error"] == "not_found"


def test_html_404_still_returns_html(client):
    """Несуществующая HTML-страница → HTML, как раньше."""
    response = client.get("/nonexistent-page")

    assert response.status_code == 404
    assert b"<html" in response.data.lower() or b"<!doctype" in response.data.lower()


def test_api_405_returns_json(client):
    """POST на GET-эндпоинт → JSON 405."""
    response = client.post("/api/v1/health")

    assert response.status_code == 405
    data = response.get_json()
    assert data["error"] == "method_not_allowed"
