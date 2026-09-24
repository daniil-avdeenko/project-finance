"""Healthcheck публичного API."""

from flask import jsonify

from app.api.v1 import api_v1_bp


@api_v1_bp.route("/health", methods=["GET"])
def api_health():
    """
    Простой healthcheck без авторизации и доступа к БД.
    """
    return jsonify({"status": "ok", "service": "project-finance-api", "version": "v1"})
