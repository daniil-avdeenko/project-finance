"""
Документация API: OpenAPI-спецификация + Swagger UI + ReDoc.

Все три эндпоинта закрыты @login_required.
"""

from functools import lru_cache

from flask import jsonify, render_template, request
from flask_login import login_required

from app.api.v1 import api_v1_bp
from app.api.v1.openapi_spec import build_openapi_spec


@lru_cache(maxsize=1)
def _build_spec_cached() -> dict:
    """
    Спецификация кэшируется после первого вызова.
    """
    return build_openapi_spec()


@api_v1_bp.route("/openapi.json", methods=["GET"])
@login_required
def api_openapi_json():
    """OpenAPI-спецификация в JSON."""
    spec = _build_spec_cached()
    # Подставляем актуальный host при каждом запросе — не кэшируем.
    spec = {**spec, "servers": [{"url": f"http://{request.host}", "description": "Current"}]}
    return jsonify(spec)


@api_v1_bp.route("/docs", methods=["GET"])
@login_required
def api_docs():
    """Swagger UI."""
    return render_template("api/swagger.html")


@api_v1_bp.route("/redoc", methods=["GET"])
@login_required
def api_redoc():
    """ReDoc — альтернативный рендерер, удобнее для чтения больших API."""
    return render_template("api/redoc.html")
