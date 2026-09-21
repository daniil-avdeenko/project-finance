"""Тесты отправки уведомлений в Telegram через httpx."""

import httpx
import pytest
import respx

from app.integrations.telegram import send_error, send_message, send_success

# ============================================================
#   ФИКСТУРЫ
# ============================================================


@pytest.fixture(autouse=True)
def telegram_env(monkeypatch):
    """Устанавливаем фиктивные токен и chat_id для всех тестов."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token-123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")


SEND_URL = "https://api.telegram.org/bottest-token-123/sendMessage"


# ============================================================
#   send_message
# ============================================================


@respx.mock
async def test_send_message_success():
    """Успешная отправка возвращает True и шлёт правильный payload."""
    route = respx.post(SEND_URL).mock(return_value=httpx.Response(200, json={"ok": True}))

    result = await send_message("Привет")

    assert result is True
    assert route.called

    import json

    body = json.loads(route.calls.last.request.content)
    assert body["chat_id"] == "123456789"
    assert body["text"] == "Привет"
    assert body["parse_mode"] == "HTML"
    assert body["disable_web_page_preview"] is True


@respx.mock
async def test_send_message_returns_false_on_4xx():
    """4xx ответ → False, без исключения."""
    respx.post(SEND_URL).mock(return_value=httpx.Response(400, json={"error": "Bad"}))

    result = await send_message("Привет")

    assert result is False


@respx.mock
async def test_send_message_returns_false_on_5xx():
    """5xx ответ → False."""
    respx.post(SEND_URL).mock(return_value=httpx.Response(500))

    result = await send_message("Привет")

    assert result is False


@respx.mock
async def test_send_message_returns_false_on_network_error():
    """Сетевая ошибка → False, не падает наружу."""
    respx.post(SEND_URL).mock(side_effect=httpx.ConnectError("Refused"))

    result = await send_message("Привет")

    assert result is False


async def test_send_message_returns_false_without_token(monkeypatch):
    """Без TELEGRAM_BOT_TOKEN возвращает False, не поднимает ValueError."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    result = await send_message("Привет")

    assert result is False


async def test_send_message_returns_false_without_chat_id(monkeypatch):
    """Без TELEGRAM_CHAT_ID возвращает False."""
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    result = await send_message("Привет")

    assert result is False


# ============================================================
#   send_error
# ============================================================


@respx.mock
async def test_send_error_formats_message():
    """send_error формирует сообщение с типом и текстом ошибки."""
    route = respx.post(SEND_URL).mock(return_value=httpx.Response(200, json={"ok": True}))

    error = ValueError("Something broke")
    result = await send_error("job_sync_grist", error)

    assert result is True

    import json

    body = json.loads(route.calls.last.request.content)
    assert "Ошибка задачи" in body["text"]
    assert "job_sync_grist" in body["text"]
    assert "ValueError" in body["text"]
    assert "Something broke" in body["text"]


@respx.mock
async def test_send_error_includes_traceback():
    """send_error добавляет трейсбек в <pre>-блок."""
    route = respx.post(SEND_URL).mock(return_value=httpx.Response(200, json={"ok": True}))

    await send_error(
        "job_test", RuntimeError("boom"), traceback_text="Traceback:\n  line 1\n  line 2"
    )

    import json

    body = json.loads(route.calls.last.request.content)
    assert "<pre>" in body["text"]
    assert "line 1" in body["text"]


@respx.mock
async def test_send_error_escapes_html():
    """Спецсимволы HTML в тексте ошибки экранируются."""
    route = respx.post(SEND_URL).mock(return_value=httpx.Response(200, json={"ok": True}))

    await send_error("job_test", ValueError("<script>alert(1)</script>"))

    import json

    body = json.loads(route.calls.last.request.content)
    assert "&lt;script&gt;" in body["text"]
    assert "<script>" not in body["text"]


# ============================================================
#   send_success
# ============================================================


@respx.mock
async def test_send_success_formats_message():
    """send_success добавляет ✅ и заголовок."""
    route = respx.post(SEND_URL).mock(return_value=httpx.Response(200, json={"ok": True}))

    result = await send_success("Синхронизация завершена", "Добавлено 5 записей")

    assert result is True

    import json

    body = json.loads(route.calls.last.request.content)
    assert "✅" in body["text"]
    assert "Синхронизация завершена" in body["text"]
    assert "Добавлено 5 записей" in body["text"]


# ============================================================
#   ЛОГИРОВАНИЕ СЕТЕВЫХ ОШИБОК
# ============================================================


@respx.mock
async def test_send_message_logs_request_error_type(caplog):
    """При RequestError логируется тип исключения, не пустая строка."""
    import logging

    caplog.set_level(logging.ERROR, logger="app.integrations.telegram")

    respx.post(SEND_URL).mock(side_effect=httpx.ReadError("Connection reset"))

    result = await send_message("test")

    assert result is False
    assert "ReadError" in caplog.text
    assert "sendMessage" in caplog.text


@respx.mock
async def test_send_message_logs_timeout(caplog):
    """Таймаут логируется отдельно от прочих сетевых ошибок."""
    import logging

    caplog.set_level(logging.ERROR, logger="app.integrations.telegram")

    respx.post(SEND_URL).mock(side_effect=httpx.ConnectTimeout("Timeout"))

    result = await send_message("test")

    assert result is False
    assert "Таймаут" in caplog.text
    assert "ConnectTimeout" in caplog.text
