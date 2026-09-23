# ============================================================
#   project-finance — единый образ для web и scheduler
# ============================================================
# Один образ, две роли: web (gunicorn) и scheduler (python -m scheduler.runner).

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    FLASK_APP=run.py

# Системные зависимости: curl для healthcheck, остальные нужны Playwright'у
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Непривилегированный пользователь
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Даём appuser права на /app — иначе setup_logging упадёт
# на создании logs/ (в docker-compose скрыто volume'ом, на Railway нет)
RUN chown appuser:appuser /app

# Requirements
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Playwright: Chromium + системные библиотеки
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN mkdir -p /ms-playwright && chown appuser:appuser /ms-playwright

RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Код приложения
COPY --chown=appuser:appuser . .

USER appuser

# Web-режим по умолчанию (scheduler переопределяет через command)
EXPOSE 5000

CMD ["gunicorn", "run:app", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "60"]
