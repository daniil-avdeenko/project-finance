"""Тесты интеграции с Google Sheets через gspread (без сети)."""

from unittest.mock import MagicMock, patch

import pytest

from app.integrations import google_sheets as gs

# ============================================================
#   ФИКСТУРЫ
# ============================================================


@pytest.fixture
def fake_project():
    class FakeProject:
        id = 1
        name = "Тестовый проект"
        description = "Описание"
        total_income = 100_000.0
        total_expense = 40_000.0
        profit = 60_000.0
        profitability = 60.0

    return FakeProject()


@pytest.fixture
def fake_transaction():
    class FakeProject:
        name = "Тестовый проект"

    class FakeTransaction:
        id = 42
        date = None
        project = FakeProject()
        type = "income"
        amount = 100.0
        currency = "USD"
        description = "Оплата"

        @property
        def amount_rub(self):
            return 8450.0

    return FakeTransaction()


@pytest.fixture
def mock_worksheet():
    """Мок gspread.Worksheet с отслеживанием вызовов."""
    ws = MagicMock()
    ws.title = "Test"
    return ws


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

    result = gs.ensure_sheets(spreadsheet, ["Projects", "Transactions"])

    # Projects уже был — add_worksheet не вызван для него
    spreadsheet.add_worksheet.assert_called_once_with(title="Transactions", rows=1000, cols=20)
    assert set(result.keys()) == {"Projects", "Transactions"}


def test_ensure_sheets_all_exist():
    """Все листы есть — add_worksheet не вызывается."""
    spreadsheet = MagicMock()
    ws1 = MagicMock()
    ws1.title = "Projects"
    ws2 = MagicMock()
    ws2.title = "Transactions"
    spreadsheet.worksheets.return_value = [ws1, ws2]

    gs.ensure_sheets(spreadsheet, ["Projects", "Transactions"])

    spreadsheet.add_worksheet.assert_not_called()


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
def test_sync_projects_writes_correct_rows(_fmt, mock_worksheet, fake_project):
    """sync_projects формирует правильный список строк."""
    count = gs.sync_projects_to_sheets(mock_worksheet, [fake_project])

    assert count == 1
    mock_worksheet.clear.assert_called_once()

    # Ищем вызов update с данными начиная с A2
    data_calls = [c for c in mock_worksheet.update.call_args_list if c.args[1].startswith("A2")]
    assert len(data_calls) == 1

    row = data_calls[0].args[0][0]
    assert row == [1, "Тестовый проект", "Описание", 100_000.0, 40_000.0, 60_000.0, 60.0]


@patch("app.integrations.google_sheets.format_cell_range")
def test_sync_projects_handles_empty_list(_fmt, mock_worksheet):
    """Пустой список — clear и headers, без update данных."""
    count = gs.sync_projects_to_sheets(mock_worksheet, [])

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
    _fmt, mock_validation, mock_worksheet, fake_transaction
):
    """sync_transactions настраивает dropdown-валидацию на колонки D и F."""
    gs.sync_transactions_to_sheets(mock_worksheet, [fake_transaction])

    # Два вызова set_data_validation — на D2:D1000 и F2:F1000
    assert mock_validation.call_count == 2
    ranges = [call.args[1] for call in mock_validation.call_args_list]
    assert "D2:D1000" in ranges
    assert "F2:F1000" in ranges


@patch("app.integrations.google_sheets.set_data_validation_for_cell_range")
@patch("app.integrations.google_sheets.format_cell_range")
def test_sync_transactions_empty_date(_fmt, _val, mock_worksheet, fake_transaction):
    """Транзакция без даты → пустая строка в колонке Date."""
    gs.sync_transactions_to_sheets(mock_worksheet, [fake_transaction])

    data_calls = [c for c in mock_worksheet.update.call_args_list if c.args[1].startswith("A2")]
    assert len(data_calls) == 1
    row = data_calls[0].args[0][0]
    assert row[1] == ""  # date → ""
    assert row[3] == "income"
    assert row[5] == "USD"
    assert row[6] == 8450.0


# ============================================================
#   sync_all_to_sheets
# ============================================================


@patch("app.integrations.google_sheets.sync_transactions_to_sheets")
@patch("app.integrations.google_sheets.sync_projects_to_sheets")
@patch("app.integrations.google_sheets.ensure_sheets")
@patch("app.integrations.google_sheets.get_spreadsheet")
def test_sync_all_calls_both(mock_spreadsheet, mock_ensure, mock_projects, mock_transactions):
    """sync_all вызывает оба sync'а и возвращает счётчики."""
    mock_ensure.return_value = {
        "Projects": MagicMock(),
        "Transactions": MagicMock(),
    }
    mock_projects.return_value = 6
    mock_transactions.return_value = 386

    result = gs.sync_all_to_sheets(projects=[], transactions=[])

    assert result == {"projects": 6, "transactions": 386}
    mock_projects.assert_called_once()
    mock_transactions.assert_called_once()


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
