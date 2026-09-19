"""Тесты security-фич."""


def test_healthz_returns_ok_without_login(client):
    """Healthcheck доступен без логина и возвращает 200 JSON."""
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
