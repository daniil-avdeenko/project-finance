"""Тесты для интеграции с Grist API через httpx."""

import json
from datetime import UTC, datetime
from datetime import date as date_cls

import httpx
import pytest
import respx

from app.integrations.grist_httpx import (
    GristClient,
    sync_projects_to_grist_httpx,
    sync_rates_to_grist_httpx,
    sync_transactions_to_grist_httpx,
)

# ============================================================
#   ФИКСТУРЫ
# ============================================================


@pytest.fixture
def grist_client():
    """Готовый клиент с фиктивными credentials."""
    return GristClient(
        api_key="test-api-key",
        doc_id="test-doc-id",
        server="https://docs.getgrist.com",
    )


@pytest.fixture
def fake_project():
    """Простой объект, имитирующий Project из SQLAlchemy."""

    class FakeProject:
        id = 1
        name = "Тестовый проект"
        description = "Описание"
        total_income = 100000.0
        total_expense = 40000.0
        profit = 60000.0
        profitability = 60.0

    return FakeProject()


@pytest.fixture
def fake_transaction():
    """Простой объект, имитирующий Transaction с подгруженным project."""

    class FakeProject:
        name = "Тестовый проект"

    class FakeTransaction:
        id = 42
        date = datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC)
        project_id = 1
        project = FakeProject()
        type = "income"
        amount = 5000.0
        description = "Оплата"

    return FakeTransaction()


# ============================================================
#   ТЕСТЫ КОНСТРУКТОРА GristClient
# ============================================================


def test_grist_client_builds_correct_base_url(grist_client):
    """base_url собирается из server и doc_id."""
    assert grist_client.base_url == "https://docs.getgrist.com/api/docs/test-doc-id"


def test_grist_client_strips_trailing_slash():
    """Хвостовой слэш в server обрезается."""
    client = GristClient("key", "doc", server="https://docs.getgrist.com/")
    assert client.base_url == "https://docs.getgrist.com/api/docs/doc"


def test_grist_client_has_auth_header(grist_client):
    """В заголовках есть Bearer-токен."""
    assert grist_client.headers["Authorization"] == "Bearer test-api-key"
    assert grist_client.headers["Content-Type"] == "application/json"


# ============================================================
#   ТЕСТЫ УСПЕШНОГО upsert_records
# ============================================================


@respx.mock
async def test_upsert_records_sends_put_with_correct_payload(grist_client):
    """upsert отправляет PUT и возвращает статистику added/updated."""
    route = respx.put(
        "https://docs.getgrist.com/api/docs/test-doc-id/tables/Projects/records"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "addRecordIds": [1, 2],
                "updateRecordIds": [3],
            },
        )
    )

    records = [{"require": {"id": 1}, "fields": {"name": "Проект"}}]
    result = await grist_client.upsert_records("Projects", records)

    assert route.called
    assert route.calls.last.request.method == "PUT"

    body = json.loads(route.calls.last.request.content)
    assert body == {"records": records}

    assert result == {"added": 2, "updated": 1}


@respx.mock
async def test_upsert_records_returns_zero_stats_on_204(grist_client):
    """При 204 No Content возвращается пустая статистика."""
    respx.put("https://docs.getgrist.com/api/docs/test-doc-id/tables/Projects/records").mock(
        return_value=httpx.Response(204)
    )

    result = await grist_client.upsert_records("Projects", [{"require": {}, "fields": {}}])

    assert result == {"added": 0, "updated": 0}


# ============================================================
#   ТЕСТЫ ОШИБОК upsert_records
# ============================================================


@respx.mock
async def test_upsert_records_raises_on_4xx(grist_client):
    """4xx ответ поднимает HTTPStatusError."""
    respx.put("https://docs.getgrist.com/api/docs/test-doc-id/tables/Projects/records").mock(
        return_value=httpx.Response(400, json={"error": "Bad request"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        await grist_client.upsert_records("Projects", [{"require": {}, "fields": {}}])


@respx.mock
async def test_upsert_records_raises_on_5xx(grist_client):
    """5xx ответ поднимает HTTPStatusError."""
    respx.put("https://docs.getgrist.com/api/docs/test-doc-id/tables/Projects/records").mock(
        return_value=httpx.Response(500)
    )

    with pytest.raises(httpx.HTTPStatusError):
        await grist_client.upsert_records("Projects", [])


@respx.mock
async def test_upsert_records_raises_on_network_error(grist_client):
    """Сетевая ошибка поднимает RequestError."""
    respx.put("https://docs.getgrist.com/api/docs/test-doc-id/tables/Projects/records").mock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    with pytest.raises(httpx.RequestError):
        await grist_client.upsert_records("Projects", [])


# ============================================================
#   ТЕСТЫ sync_projects_to_grist_httpx
# ============================================================


@respx.mock
async def test_sync_projects_sends_correct_records(monkeypatch, fake_project):
    """sync_projects формирует правильные записи."""
    monkeypatch.setenv("GRIST_API_KEY", "test-key")
    monkeypatch.setenv("GRIST_DOC_ID", "test-doc")

    route = respx.put("https://docs.getgrist.com/api/docs/test-doc/tables/Projects/records").mock(
        return_value=httpx.Response(200, json={"addRecordIds": [1]})
    )

    await sync_projects_to_grist_httpx([fake_project])

    body = json.loads(route.calls.last.request.content)
    record = body["records"][0]

    assert record["require"] == {"ID2": 1}
    assert record["fields"]["A"] == "Тестовый проект"
    assert record["fields"]["B"] == "Описание"
    assert record["fields"]["C"] == 100000.0
    assert record["fields"]["D"] == 40000.0
    assert record["fields"]["E"] == 60000.0
    assert record["fields"]["F"] == 60.0


@respx.mock
async def test_sync_projects_skips_empty_list(monkeypatch):
    """Пустой список — не делаем запрос."""
    monkeypatch.setenv("GRIST_API_KEY", "test-key")
    monkeypatch.setenv("GRIST_DOC_ID", "test-doc")

    route = respx.put("https://docs.getgrist.com/api/docs/test-doc/tables/Projects/records").mock(
        return_value=httpx.Response(200, json={"addRecordIds": []})
    )

    await sync_projects_to_grist_httpx([])

    assert not route.called


# ============================================================
#   ТЕСТЫ sync_transactions_to_grist_httpx
# ============================================================


@respx.mock
async def test_sync_transactions_sends_correct_fields(monkeypatch, fake_transaction):
    """Проверяем формирование полей транзакции."""
    monkeypatch.setenv("GRIST_API_KEY", "test-key")
    monkeypatch.setenv("GRIST_DOC_ID", "test-doc")

    route = respx.put(
        "https://docs.getgrist.com/api/docs/test-doc/tables/Transactions/records"
    ).mock(return_value=httpx.Response(200, json={"addRecordIds": [42]}))

    await sync_transactions_to_grist_httpx([fake_transaction])

    body = json.loads(route.calls.last.request.content)
    record = body["records"][0]

    assert record["require"] == {"ID2": 42}
    assert record["fields"]["A"] == "2026-09-15T12:00:00"
    assert record["fields"]["ID_"] == 1
    assert record["fields"]["B"] == "Тестовый проект"
    assert record["fields"]["C"] == "income"
    assert record["fields"]["D"] == 5000.0
    assert record["fields"]["E"] == "Оплата"


@respx.mock
async def test_sync_transactions_skips_empty_list(monkeypatch):
    """Пустой список — не делаем запрос."""
    monkeypatch.setenv("GRIST_API_KEY", "test-key")
    monkeypatch.setenv("GRIST_DOC_ID", "test-doc")

    route = respx.put(
        "https://docs.getgrist.com/api/docs/test-doc/tables/Transactions/records"
    ).mock(return_value=httpx.Response(200, json={"addRecordIds": []}))

    await sync_transactions_to_grist_httpx([])

    assert not route.called


# ============================================================
#   ТЕСТЫ ВАЛИДАЦИИ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ
# ============================================================


async def test_sync_projects_requires_api_key(monkeypatch):
    """Без GRIST_API_KEY поднимается ValueError."""
    monkeypatch.delenv("GRIST_API_KEY", raising=False)
    monkeypatch.setenv("GRIST_DOC_ID", "test-doc")

    with pytest.raises(ValueError, match="GRIST_API_KEY"):
        await sync_projects_to_grist_httpx([])


async def test_sync_projects_requires_doc_id(monkeypatch):
    """Без GRIST_DOC_ID поднимается ValueError."""
    monkeypatch.setenv("GRIST_API_KEY", "test-key")
    monkeypatch.delenv("GRIST_DOC_ID", raising=False)

    with pytest.raises(ValueError, match="GRIST_DOC_ID"):
        await sync_projects_to_grist_httpx([])


# ============================================================
#   sync_rates_to_grist_httpx
# ============================================================


@pytest.fixture
def fake_rate():
    """Минимальный ScrapedRate-подобный объект."""

    class FakeRate:
        code = "USD"
        nominal = 1
        rate = 84.5093
        rate_date = date_cls(2026, 9, 18)

    return FakeRate()


@respx.mock
async def test_sync_rates_sends_correct_payload(monkeypatch, fake_rate):
    """Проверяем формирование полей курса."""
    monkeypatch.setenv("GRIST_API_KEY", "test-key")
    monkeypatch.setenv("GRIST_DOC_ID", "test-doc")

    route = respx.put(
        "https://docs.getgrist.com/api/docs/test-doc/tables/ExchangeRates/records"
    ).mock(return_value=httpx.Response(200, json={"addRecordIds": [1]}))

    await sync_rates_to_grist_httpx([fake_rate])

    body = json.loads(route.calls.last.request.content)
    record = body["records"][0]

    assert record["require"] == {"ID2": "USD"}
    assert record["fields"]["A"] == "2026-09-18"
    assert record["fields"]["B"] == "USD"
    assert record["fields"]["C"] == 1
    assert record["fields"]["D"] == 84.5093


@respx.mock
async def test_sync_rates_skips_empty_list(monkeypatch):
    """Пустой список — запрос не делается."""
    monkeypatch.setenv("GRIST_API_KEY", "test-key")
    monkeypatch.setenv("GRIST_DOC_ID", "test-doc")

    route = respx.put("https://docs.grist.com/api/docs/test-doc/tables/ExchangeRates/records").mock(
        return_value=httpx.Response(200, json={"addRecordIds": []})
    )

    await sync_rates_to_grist_httpx([])

    assert not route.called
