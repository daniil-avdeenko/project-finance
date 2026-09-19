"""
HTTP security headers.

Подключается через app.after_request в create_app.
"""

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
