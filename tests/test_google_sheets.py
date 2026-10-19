"""Тесты интеграции с Google Sheets через gspread (без сети)."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest
from gspread.exceptions import APIError

from app.integrations import google_sheets as gs

# ============================================================
#   ФИКСТУРЫ
# ============================================================


@pytest.fixture
def fake_transaction():
    """Простой объект, имитирующий Transaction с подгруженным project."""

    class FakeProject:
        name = "Тестовый проект"

    class FakeTransaction:
        id = 42
        date = datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC)
        project_id = 1
        project = FakeProject()
        type = "income"
        amount = 5000.0
        currency = "USD"
        description = "Оплата"

    return FakeTransaction()


@pytest.fixture
def fake_rates_map():
    """rates_map для конвертации в тестах."""
    from datetime import date as date_cls

    class FakeRate:
        code = "USD"
        rate_date = date_cls(2026, 9, 15)
        nominal = 1
        rate_rub = 84.50

    return {"USD": [FakeRate()]}


@pytest.fixture
def mock_worksheet():
    """Мок gspread.Worksheet с отслеживанием вызовов."""
    ws = MagicMock()
    ws.title = "Test"
    return ws


def _make_response(status: int):
    """Fake httpx.Response с нужным статусом для gspread.APIError."""
    from httpx import Response

    return Response(status_code=status)


# ============================================================
#   get_client / get_spreadsheet — валидация env
# ============================================================


def test_get_client_raises_if_credentials_missing(monkeypatch, tmp_path):
    """Нет файла credentials.json — FileNotFoundError."""
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", str(tmp_path / "nope.json"))

    with pytest.raises(FileNotFoundError, match="nope.json"):
        gs.get_client()


def test_get_spreadsheet_raises_without_id(monkeypatch):
    """Нет GOOGLE_SPREADSHEET_ID — ValueError."""
    monkeypatch.delenv("GOOGLE_SPREADSHEET_ID", raising=False)

    with pytest.raises(ValueError, match="GOOGLE_SPREADSHEET_ID"):
        gs.get_spreadsheet()


# ============================================================
#   ensure_sheets
# ============================================================


def test_ensure_sheets_creates_missing():
    """Отсутствующие листы создаются, существующие — не трогаются."""
    spreadsheet = MagicMock()
    existing_ws = MagicMock()
    existing_ws.title = "Projects"
    spreadsheet.worksheets.return_value = [existing_ws]

    created = MagicMock()
    created.title = "Transactions"
    spreadsheet.worksheet.return_value = created

    sheets, created_names = gs.ensure_sheets(spreadsheet, ["Projects", "Transactions"])

    # Projects уже был — add_worksheet не вызван для него
    spreadsheet.add_worksheet.assert_called_once_with(title="Transactions", rows=1000, cols=20)
    assert set(sheets.keys()) == {"Projects", "Transactions"}
    # Вернулось множество созданных листов — только Transactions
    assert created_names == {"Transactions"}


def test_ensure_sheets_all_exist():
    """Все листы есть — add_worksheet не вызывается."""
    spreadsheet = MagicMock()
    ws1 = MagicMock()
    ws1.title = "Projects"
    ws2 = MagicMock()
    ws2.title = "Transactions"
    spreadsheet.worksheets.return_value = [ws1, ws2]

    sheets, created_names = gs.ensure_sheets(spreadsheet, ["Projects", "Transactions"])

    spreadsheet.add_worksheet.assert_not_called()
    assert created_names == set()  # ни одного нового листа


# ============================================================
#   apply_headers
# ============================================================


@patch("app.integrations.google_sheets.format_cell_range")
def test_apply_headers_writes_and_formats(mock_format, mock_worksheet):
    """apply_headers пишет заголовки и форматирует строку A1:<last>1."""
    headers = ["ID", "Name", "Value"]
    gs.apply_headers(mock_worksheet, headers)

    mock_worksheet.update.assert_called_once_with([headers], "A1")
    # Последняя колонка для 3 заголовков — C
    assert mock_format.called
    assert "A1:C1" in str(mock_format.call_args)


# ============================================================
#   sync_projects_to_sheets
# ============================================================


@patch("app.integrations.google_sheets.format_cell_range")
def test_sync_projects_writes_correct_rows(_fmt, mock_worksheet):
    """sync_projects формирует правильный список строк из stats_map."""
    from app.services.project_stats import ProjectStats

    class FakeProject:
        id = 1
        name = "Тестовый проект"
        description = "Описание"

    stats_map = {1: ProjectStats(100_000.0, 40_000.0, 60_000.0, 60.0)}

    count = gs.sync_projects_to_sheets(mock_worksheet, [FakeProject()], stats_map)

    assert count == 1
    mock_worksheet.clear.assert_called_once()

    data_calls = [c for c in mock_worksheet.update.call_args_list if c.args[1].startswith("A2")]
    assert len(data_calls) == 1

    row = data_calls[0].args[0][0]
    assert row == [1, "Тестовый проект", "Описание", 100_000.0, 40_000.0, 60_000.0, 60.0]


@patch("app.integrations.google_sheets.format_cell_range")
def test_sync_projects_handles_empty_list(_fmt, mock_worksheet):
    """Пустой список — clear и headers, без update данных."""
    count = gs.sync_projects_to_sheets(mock_worksheet, [], {})

    assert count == 0
    mock_worksheet.clear.assert_called_once()
    # Данные не писались (update только для заголовков на A1)
    data_calls = [c for c in mock_worksheet.update.call_args_list if c.args[1].startswith("A2")]
    assert data_calls == []


# ============================================================
#   sync_transactions_to_sheets
# ============================================================


@patch("app.integrations.google_sheets.set_data_validation_for_cell_range")
@patch("app.integrations.google_sheets.format_cell_range")
def test_sync_transactions_applies_validation(
    _fmt, mock_validation, mock_worksheet, fake_transaction, fake_rates_map
):
    """sync_transactions настраивает dropdown-валидацию на колонки D и F."""
    gs.sync_transactions_to_sheets(mock_worksheet, [fake_transaction], fake_rates_map)

    assert mock_validation.call_count == 2
    ranges = [call.args[1] for call in mock_validation.call_args_list]
    assert "D2:D1000" in ranges
    assert "F2:F1000" in ranges


@patch("app.integrations.google_sheets.set_data_validation_for_cell_range")
@patch("app.integrations.google_sheets.format_cell_range")
def test_sync_transactions_empty_date(_fmt, _val, mock_worksheet, fake_rates_map):
    """Транзакция без даты → пустая строка в колонке Date, сумма из rates_map."""

    class FakeProject:
        name = "Тестовый проект"

    class FakeTransaction:
        id = 42
        date = None
        project_id = 1
        project = FakeProject()
        type = "income"
        amount = 100.0
        currency = "USD"
        description = "Оплата"

    tx = FakeTransaction()

    gs.sync_transactions_to_sheets(mock_worksheet, [tx], fake_rates_map)

    data_calls = [c for c in mock_worksheet.update.call_args_list if c.args[1].startswith("A2")]
    assert len(data_calls) == 1
    row = data_calls[0].args[0][0]
    assert row[1] == ""  # date → ""
    assert row[3] == "income"
    assert row[5] == "USD"
    assert row[6] == 8450.0  # 100 USD * 84.50


@patch("app.integrations.google_sheets.set_data_validation_for_cell_range")
@patch("app.integrations.google_sheets.format_cell_range")
def test_sync_transactions_skips_validation_on_existing_sheet(
    _fmt, mock_validation, mock_worksheet, fake_transaction, fake_rates_map
):
    """При is_new_sheet=False валидация не применяется — экономия запросов."""
    gs.sync_transactions_to_sheets(
        mock_worksheet, [fake_transaction], fake_rates_map, is_new_sheet=False
    )
    mock_validation.assert_not_called()


# ============================================================
#   sync_all_to_sheets
# ============================================================


@patch("app.integrations.google_sheets.sync_exchange_rates_to_sheets")
@patch("app.integrations.google_sheets.sync_transactions_to_sheets")
@patch("app.integrations.google_sheets.sync_projects_to_sheets")
@patch("app.integrations.google_sheets.ensure_sheets")
@patch("app.integrations.google_sheets.get_spreadsheet")
def test_sync_all_calls_both(
    mock_spreadsheet, mock_ensure, mock_projects, mock_transactions, mock_rates
):
    """sync_all вызывает все три sync'а и возвращает счётчики."""
    mock_ensure.return_value = (
        {"Projects": MagicMock(), "Transactions": MagicMock(), "ExchangeRates": MagicMock()},
        set(),
    )
    mock_projects.return_value = 6
    mock_transactions.return_value = 386
    mock_rates.return_value = 3

    result = gs.sync_all_to_sheets(projects=[], transactions=[], rates=[])

    assert result == {"projects": 6, "transactions": 386, "rates": 3}
    mock_projects.assert_called_once()
    mock_transactions.assert_called_once()
    mock_rates.assert_called_once()
    assert mock_transactions.call_args.kwargs.get("is_new_sheet") is False


@patch("app.integrations.google_sheets.sync_exchange_rates_to_sheets")
@patch("app.integrations.google_sheets.sync_transactions_to_sheets")
@patch("app.integrations.google_sheets.sync_projects_to_sheets")
@patch("app.integrations.google_sheets.ensure_sheets")
@patch("app.integrations.google_sheets.get_spreadsheet")
def test_sync_all_applies_formatting_on_new_sheet(
    mock_spreadsheet, mock_ensure, mock_projects, mock_transactions, mock_rates
):
    """Если лист Transactions создан впервые — is_new_sheet=True."""
    mock_ensure.return_value = (
        {"Projects": MagicMock(), "Transactions": MagicMock(), "ExchangeRates": MagicMock()},
        {"Transactions"},
    )
    mock_projects.return_value = 6
    mock_transactions.return_value = 100
    mock_rates.return_value = 3

    gs.sync_all_to_sheets(projects=[], transactions=[], rates=[])

    assert mock_transactions.call_args.kwargs.get("is_new_sheet") is True


# ============================================================
#   apply_number_format_formats_amount_columns
# ============================================================


@patch("app.integrations.google_sheets.format_cell_range")
def test_apply_number_format_formats_amount_columns(mock_format, mock_worksheet):
    """apply_number_format форматирует колонки E и G числовым паттерном."""
    gs.apply_number_format(mock_worksheet)

    assert mock_format.call_count == 2

    ranges = [call.args[1] for call in mock_format.call_args_list]
    assert "E2:E1000" in ranges
    assert "G2:G1000" in ranges

    # Проверяем сам формат
    for call in mock_format.call_args_list:
        fmt = call.args[2]
        assert fmt.numberFormat.type == "NUMBER"
        assert fmt.numberFormat.pattern == "#,##0.00"


# ============================================================
#   GOOGLE_CREDENTIALS_B64
# ============================================================


def test_get_client_uses_b64_if_set(monkeypatch):
    """GOOGLE_CREDENTIALS_B64 имеет приоритет над файлом."""
    import base64
    import json
    from unittest.mock import patch

    fake_key = "-----BEGIN " + "PRIVATE KEY-----" + "\nMIIB\n" + "-----END PRIVATE KEY-----" + "\n"

    fake_creds = {
        "type": "service_account",
        "project_id": "test",
        "private_key_id": "abc",
        "private_key": fake_key,
        "client_email": "test@test.iam.gserviceaccount.com",
        "client_id": "123",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    b64 = base64.b64encode(json.dumps(fake_creds).encode()).decode()

    monkeypatch.setenv("GOOGLE_CREDENTIALS_B64", b64)

    with (
        patch("app.integrations.google_sheets.Credentials") as mock_creds,
        patch("app.integrations.google_sheets.gspread"),
    ):
        gs.get_client()

        assert mock_creds.from_service_account_info.called
        assert not mock_creds.from_service_account_file.called


def test_get_client_raises_on_invalid_b64(monkeypatch):
    """Битый base64 → ValueError с понятным сообщением."""
    monkeypatch.setenv("GOOGLE_CREDENTIALS_B64", "not-valid-base64!!!")

    with pytest.raises(ValueError, match="не декодируется"):
        gs.get_client()


def test_get_client_falls_back_to_file(monkeypatch, tmp_path):
    """Без B64 — используется файл. Нет файла — FileNotFoundError."""
    monkeypatch.delenv("GOOGLE_CREDENTIALS_B64", raising=False)
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", str(tmp_path / "nope.json"))

    with pytest.raises(FileNotFoundError):
        gs.get_client()


# ============================================================
#   sync_exchange_rates_to_sheets
# ============================================================


@patch("app.integrations.google_sheets.format_cell_range")
def test_sync_exchange_rates_writes_rows(_fmt, mock_worksheet):
    """Формирует по одной строке на курс, сортировка — по алфавиту."""

    class FakeRate:
        def __init__(self, code, nominal, rate_rub, rate_date):
            self.code = code
            self.nominal = nominal
            self.rate_rub = rate_rub
            self.rate_date = rate_date

    rates = [
        FakeRate("CNY", 1, 12.15, date(2026, 9, 19)),
        FakeRate("EUR", 1, 97.30, date(2026, 9, 19)),
        FakeRate("USD", 1, 84.50, date(2026, 9, 19)),
    ]

    count = gs.sync_exchange_rates_to_sheets(mock_worksheet, rates)

    assert count == 3
    data_calls = [c for c in mock_worksheet.update.call_args_list if c.args[1].startswith("A2")]
    assert len(data_calls) == 1
    rows = data_calls[0].args[0]
    assert rows[0] == ["CNY", 1, 12.15, "2026-09-19"]
    assert rows[2] == ["USD", 1, 84.50, "2026-09-19"]


@patch("app.integrations.google_sheets.format_cell_range")
def test_sync_exchange_rates_empty(_fmt, mock_worksheet):
    """Пустой список курсов — только заголовки, без данных."""
    count = gs.sync_exchange_rates_to_sheets(mock_worksheet, [])

    assert count == 0
    data_calls = [c for c in mock_worksheet.update.call_args_list if c.args[1].startswith("A2")]
    assert data_calls == []


def test_fill_worksheet_retries_on_429(mock_worksheet, monkeypatch):
    """429 → retry, следующий вызов успешен."""
    from app.integrations import google_sheets as gs

    mock_worksheet.clear.side_effect = [
        APIError(_make_response(429)),
        None,
    ]
    monkeypatch.setattr(gs.time, "sleep", lambda _: None)  # ускоряем тест

    gs._fill_worksheet(mock_worksheet, ["A"], [["x"]])

    assert mock_worksheet.clear.call_count == 2


def test_fill_worksheet_gives_up_after_max_attempts(mock_worksheet, monkeypatch):
    """5xx на всех попытках → APIError пробрасывается."""
    from app.integrations import google_sheets as gs

    mock_worksheet.clear.side_effect = APIError(_make_response(500))
    monkeypatch.setattr(gs.time, "sleep", lambda _: None)

    with pytest.raises(APIError):
        gs._fill_worksheet(mock_worksheet, ["A"], [["x"]])

    assert mock_worksheet.clear.call_count == 3


def test_fill_worksheet_does_not_retry_on_4xx(mock_worksheet, monkeypatch):
    """403 → сразу raise, без retry."""
    from app.integrations import google_sheets as gs

    mock_worksheet.clear.side_effect = APIError(_make_response(403))
    monkeypatch.setattr(gs.time, "sleep", lambda _: None)

    with pytest.raises(APIError):
        gs._fill_worksheet(mock_worksheet, ["A"], [["x"]])

    assert mock_worksheet.clear.call_count == 1
