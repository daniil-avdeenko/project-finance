"""
Синхронизация данных в Google Sheets через gspread.
В scheduler вызывается через asyncio.to_thread, чтобы не блокировать event loop.
"""

import logging
import os
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials
from gspread_formatting import (
    BooleanCondition,
    CellFormat,
    Color,
    DataValidationRule,
    NumberFormat,
    TextFormat,
    format_cell_range,
    set_data_validation_for_cell_range,
)

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

PROJECTS_HEADERS = [
    "ID",
    "Название",
    "Описание",
    "Доходы",
    "Расходы",
    "Прибыль",
    "Рентабельность, %",
]
TRANSACTIONS_HEADERS = [
    "ID",
    "Дата",
    "Проект",
    "Тип",
    "Сумма",
    "Валюта",
    "Сумма (RUB)",
    "Описание",
]

VALID_TRANSACTION_TYPES = ["income", "expense"]
VALID_CURRENCIES = ["RUB", "USD", "EUR"]


def get_client() -> gspread.Client:
    """Авторизует gspread через service account."""
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
    if not Path(creds_path).exists():
        raise FileNotFoundError(f"Файл с учетными данными не найден: {creds_path}")

    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return gspread.authorize(creds)


def get_spreadsheet() -> gspread.Spreadsheet:
    """Открывает таблицу по ID из GOOGLE_SPREADSHEET_ID."""
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")
    if not spreadsheet_id:
        raise ValueError("Переменная окружения GOOGLE_SPREADSHEET_ID не установлена")

    client = get_client()
    return client.open_by_key(spreadsheet_id)


def ensure_sheets(
    spreadsheet: gspread.Spreadsheet, names: list[str]
) -> dict[str, gspread.Worksheet]:
    """Создаёт листы, если их нет. Возвращает {name: worksheet}."""
    existing = {ws.title for ws in spreadsheet.worksheets()}
    for name in names:
        if name not in existing:
            spreadsheet.add_worksheet(title=name, rows=1000, cols=20)
            logger.info("Создан лист: %s", name)

    return {name: spreadsheet.worksheet(name) for name in names}


def apply_headers(worksheet: gspread.Worksheet, headers: list[str]) -> None:
    """Записывает заголовки и форматирует их (жирный, серый фон)."""
    worksheet.update([headers], "A1")

    fmt = CellFormat(
        backgroundColor=Color(0.9, 0.9, 0.9),
        textFormat=TextFormat(bold=True),
    )
    last_col_letter = chr(ord("A") + len(headers) - 1)
    format_cell_range(worksheet, f"A1:{last_col_letter}1", fmt)


def apply_validation(worksheet: gspread.Worksheet) -> None:
    """
    Настраивает dropdown-валидацию для листа Transactions.

    - Колонка D (Тип)     — income / expense
    - Колонка F (Валюта)  — RUB / USD / EUR
    """
    type_rule = DataValidationRule(
        BooleanCondition("ONE_OF_LIST", VALID_TRANSACTION_TYPES),
        showCustomUi=True,
    )
    set_data_validation_for_cell_range(worksheet, "D2:D1000", type_rule)

    currency_rule = DataValidationRule(
        BooleanCondition("ONE_OF_LIST", VALID_CURRENCIES),
        showCustomUi=True,
    )
    set_data_validation_for_cell_range(worksheet, "F2:F1000", currency_rule)


def _fill_worksheet(worksheet: gspread.Worksheet, headers: list[str], rows: list[list]) -> None:
    """Очищает лист, пишет заголовки и данные одним вызовом."""
    worksheet.clear()
    apply_headers(worksheet, headers)
    if rows:
        worksheet.update(rows, "A2")


def sync_projects_to_sheets(worksheet: gspread.Worksheet, projects: list) -> int:
    """Экспортирует проекты. Возвращает количество строк."""
    rows = [
        [
            p.id,
            p.name,
            p.description or "",
            round(p.total_income, 2),
            round(p.total_expense, 2),
            round(p.profit, 2),
            p.profitability,
        ]
        for p in projects
    ]
    _fill_worksheet(worksheet, PROJECTS_HEADERS, rows)
    return len(rows)


def sync_transactions_to_sheets(worksheet: gspread.Worksheet, transactions: list) -> int:
    """Экспортирует транзакции. Возвращает количество строк."""
    rows = [
        [
            t.id,
            t.date.strftime("%Y-%m-%d") if t.date else "",
            t.project.name if t.project else "",
            t.type,
            round(t.amount, 2),
            t.currency or "RUB",
            t.amount_rub,
            t.description or "",
        ]
        for t in transactions
    ]
    _fill_worksheet(worksheet, TRANSACTIONS_HEADERS, rows)
    apply_validation(worksheet)
    apply_number_format(worksheet)
    return len(rows)


def sync_all_to_sheets(projects: list, transactions: list) -> dict[str, int]:
    """
    Полная синхронизация: проекты + транзакции.

    Возвращает {'projects': N, 'transactions': M}.
    Синхронная — из scheduler вызывается через asyncio.to_thread.
    """
    spreadsheet = get_spreadsheet()
    sheets = ensure_sheets(spreadsheet, ["Projects", "Transactions"])

    n_projects = sync_projects_to_sheets(sheets["Projects"], projects)
    n_transactions = sync_transactions_to_sheets(sheets["Transactions"], transactions)

    logger.info(
        "Google Sheets: экспортировано %d проектов, %d транзакций",
        n_projects,
        n_transactions,
    )
    return {"projects": n_projects, "transactions": n_transactions}


def apply_number_format(worksheet: gspread.Worksheet) -> None:
    """Числовой формат для колонок Amount (E) и Amount RUB (G)."""
    number_format = CellFormat(
        numberFormat=NumberFormat(type="NUMBER", pattern="#,##0.00"),
    )
    format_cell_range(worksheet, "E2:E1000", number_format)
    format_cell_range(worksheet, "G2:G1000", number_format)
