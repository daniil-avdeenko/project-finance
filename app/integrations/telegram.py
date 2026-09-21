"""
Отправка уведомлений в Telegram через Bot API.

Использует httpx.AsyncClient. Не поднимает исключения наружу —
возвращает bool, чтобы вызывающий код решал, что делать.
"""

import logging
import os
from html import escape

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
TIMEOUT_SECONDS = 10.0


def _get_config() -> tuple[str, str]:
    """Возвращает (token, chat_id) или поднимает ValueError, если их нет."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен")
    if not chat_id:
        raise ValueError("TELEGRAM_CHAT_ID не установлен")

    return token, chat_id


async def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """
    Отправляет текстовое сообщение в настроенный чат.

    Возвращает True при успехе, False при любой ошибке.
    Никогда не поднимает исключений наружу.
    """
    try:
        token, chat_id = _get_config()
    except ValueError as e:
        logger.error("Конфигурация Telegram неполная: %s", e)
        return False

    url = f"{API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            logger.error(
                "Telegram ответил %d при POST %s: %s",
                e.response.status_code,
                url,
                e.response.text[:500],
            )
            return False
        except httpx.TimeoutException as e:
            logger.error(
                "Таймаут Telegram при POST %s: %s — %r",
                url,
                type(e).__name__,
                e,
            )
            return False
        except httpx.RequestError as e:
            logger.error(
                "Сетевая ошибка Telegram при POST %s: %s — %r",
                url,
                type(e).__name__,
                e,
            )
            return False


async def send_error(task_name: str, error: Exception, traceback_text: str = "") -> bool:
    """
    Форматирует и отправляет сообщение об ошибке задачи.

    Значения санитизируются: если в трейсбеке окажется токен или пароль,
    в Telegram уйдёт ***.
    """
    from app.security import sanitize_secrets

    error_type = type(error).__name__
    error_msg = sanitize_secrets(str(error))
    task_name_safe = sanitize_secrets(task_name)

    parts = [
        "❌ <b>Ошибка задачи</b>",
        "",
        f"<b>Задача:</b> <code>{escape(task_name_safe)}</code>",
        f"<b>Тип:</b> <code>{escape(error_type)}</code>",
        f"<b>Сообщение:</b> {escape(error_msg)}",
    ]

    if traceback_text:
        trimmed = sanitize_secrets(traceback_text)[-1500:]
        parts.append("")
        parts.append(f"<pre>{escape(trimmed)}</pre>")

    return await send_message("\n".join(parts))


async def send_success(title: str, body: str) -> bool:
    """Форматирует и отправляет сообщение об успехе."""
    text = f"✅ <b>{escape(title)}</b>\n\n{body}"
    return await send_message(text)
