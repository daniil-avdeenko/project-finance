"""Blueprint публичного API v1."""

from flask import Blueprint

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

# Импортируем роуты — регистрируют эндпоинты на blueprint
from app.api.v1.routes import health  # noqa: E402, F401
