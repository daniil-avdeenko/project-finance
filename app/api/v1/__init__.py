"""Blueprint публичного API v1."""

from flask import Blueprint

from app import limiter

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

# Импортируем роуты — регистрируют эндпоинты на blueprint
from app.api.v1.routes import currencies, docs, health, projects  # noqa: E402, F401

# Rate limiting для всего API — 60 запросов в минуту на IP.
limiter.limit("60 per minute")(api_v1_bp)
