"""
OpenAPI 3.0 спецификация публичного API.
"""


def build_openapi_spec() -> dict:
    """
    Возвращает OpenAPI-спецификацию как dict.

    servers намеренно не заполнен — host подставляется в роуте
    при рендере, чтобы кэш работал между окружениями.
    """
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Project Finance API",
            "version": "1.0.0",
            "description": (
                "Публичный REST API для системы учёта финансов проектов. "
                "Rate limit: 60 запросов в минуту на IP."
            ),
        },
        "servers": [],  # заполняется в роуте
        "tags": [
            {"name": "health", "description": "Проверка доступности"},
            {"name": "stats", "description": "Аналитика и статистика"},
            {"name": "projects", "description": "Проекты"},
            {"name": "transactions", "description": "Транзакции"},
            {"name": "currencies", "description": "Курсы валют"},
        ],
        "paths": {
            "/api/v1/health": {
                "get": {
                    "tags": ["health"],
                    "summary": "Healthcheck",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/api/v1/summary": {
                "get": {
                    "tags": ["stats"],
                    "summary": "Сводка по всем проектам",
                    "parameters": [
                        {
                            "name": "date_from",
                            "in": "query",
                            "schema": {"type": "string", "format": "date"},
                        },
                        {
                            "name": "date_to",
                            "in": "query",
                            "schema": {"type": "string", "format": "date"},
                        },
                    ],
                    "responses": {
                        "200": {"description": "Сводка"},
                        "400": {"description": "Некорректный формат даты"},
                    },
                }
            },
            "/api/v1/projects": {
                "get": {
                    "tags": ["projects"],
                    "summary": "Список проектов с финансами",
                    "parameters": [
                        {
                            "name": "date_from",
                            "in": "query",
                            "schema": {"type": "string", "format": "date"},
                        },
                        {
                            "name": "date_to",
                            "in": "query",
                            "schema": {"type": "string", "format": "date"},
                        },
                        {
                            "name": "sort",
                            "in": "query",
                            "schema": {
                                "type": "string",
                                "enum": ["name_asc", "name_desc", "profit_asc", "profit_desc"],
                            },
                        },
                    ],
                    "responses": {"200": {"description": "Список"}},
                }
            },
            "/api/v1/projects/{project_id}": {
                "get": {
                    "tags": ["projects"],
                    "summary": "Детали проекта",
                    "parameters": [
                        {
                            "name": "project_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        }
                    ],
                    "responses": {
                        "200": {"description": "Детали проекта"},
                        "404": {"description": "Проект не найден"},
                    },
                }
            },
            "/api/v1/transactions": {
                "get": {
                    "tags": ["transactions"],
                    "summary": "Список транзакций с фильтрами",
                    "parameters": [
                        {
                            "name": "date_from",
                            "in": "query",
                            "schema": {"type": "string", "format": "date"},
                        },
                        {
                            "name": "date_to",
                            "in": "query",
                            "schema": {"type": "string", "format": "date"},
                        },
                        {
                            "name": "type",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["income", "expense"]},
                        },
                        {
                            "name": "currency",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["RUB", "USD", "EUR"]},
                        },
                        {"name": "project_id", "in": "query", "schema": {"type": "integer"}},
                        {
                            "name": "page",
                            "in": "query",
                            "schema": {"type": "integer", "default": 1},
                        },
                        {
                            "name": "per_page",
                            "in": "query",
                            "schema": {"type": "integer", "default": 50, "maximum": 200},
                        },
                    ],
                    "responses": {"200": {"description": "Список с пагинацией"}},
                }
            },
            "/api/v1/currencies": {
                "get": {
                    "tags": ["currencies"],
                    "summary": "Актуальные курсы USD/EUR",
                    "responses": {"200": {"description": "Курсы"}},
                }
            },
        },
    }
