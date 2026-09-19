"""
HTTP security headers.

Подключается через app.after_request в create_app.
"""

import re

from flask import Flask, Response

# CSP под наш стек: Bootstrap, Font Awesome, Chart.js с CDN + inline-скрипты
# в шаблонах. unsafe-inline ослабляет защиту, но без nonce сломает UI.
CSP = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
    "font-src 'self' https://cdnjs.cloudflare.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'self'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


def register_security_headers(app: Flask) -> None:
    """Добавляет security headers ко всем ответам."""

    @app.after_request
    def _add_headers(response: Response) -> Response:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        response.headers.setdefault("Content-Security-Policy", CSP)
        return response


_SECRET_PATTERNS = [
    # TOKEN=xxx, SECRET_KEY: "xxx", PASSWORD='xxx'
    # Порядок альтернатив: длинные — раньше коротких
    (
        re.compile(
            r"((?:SECRET_KEY|API_KEY|APIKEY|ACCESS_KEY|PRIVATE_KEY|SECRET|TOKEN|PASSWORD)"
            r"\s*[=:]\s*[\"']?)"
            r"([^\s\"']+)",
            re.IGNORECASE,
        ),
        r"\1***",
    ),
    # Bearer xxx
    (
        re.compile(r"(Bearer\s+)([A-Za-z0-9\-._~+/]+=*)", re.IGNORECASE),
        r"\1***",
    ),
    # Telegram bot token (1234567890:AAH-...)
    (
        re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b"),
        "***",
    ),
]


def sanitize_secrets(text: str) -> str:
    """Заменяет значения секретов на ***."""
    if not text:
        return text
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text
