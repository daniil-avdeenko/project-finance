"""
HTTP security headers.

Подключается через app.after_request в create_app.
"""

import re

from flask import Flask, Response

# Базовая CSP — то, что нужно всегда.
# upgrade-insecure-requests — отдельно: имеет смысл только когда приложение
# реально обслуживается по HTTPS. В dev при доступе с телефона по HTTP
# (192.168.x.x) эта директива апгрейдит form submissions до HTTPS, которые
# падают (нет TLS-сервера), и POST /login вообще не доходит до gunicorn.
# На localhost / 127.0.0.1 браузер её игнорирует — поэтому на десктопе
# проблема незаметна.
CSP_BASE = (
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

CSP_UPGRADE = "; upgrade-insecure-requests"


def _build_csp(include_upgrade: bool) -> str:
    """Собирает CSP, добавляя upgrade-insecure-requests только для HTTPS-окружений."""
    return CSP_BASE + (CSP_UPGRADE if include_upgrade else "")


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
        # SESSION_COOKIE_SECURE — прокси для «мы работаем по HTTPS».
        # Если cookies требуют Secure, значит страницы обслуживаются по TLS,
        # и upgrade-insecure-requests имеет смысл. В dev (HTTP) — нет.
        include_upgrade = bool(app.config.get("SESSION_COOKIE_SECURE", True))
        response.headers.setdefault("Content-Security-Policy", _build_csp(include_upgrade))
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
