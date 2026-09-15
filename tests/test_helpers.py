from app.helpers import parse_ids_from_string, make_csv_response


def test_parse_ids_from_string():
    """Проверяем парсинг строки с ID."""
    assert parse_ids_from_string("1,2,3") == [1, 2, 3]
    assert parse_ids_from_string("") == []
    assert parse_ids_from_string("1,abc,3") == [1, 3]     # мусор игнорируется
    assert parse_ids_from_string(" 1 , 2 ") == [1, 2]     # пробелы не мешают
    assert parse_ids_from_string("42") == [42]            # одно значение


def test_make_csv_response():
    """Проверяем, что CSV-ответ формируется с BOM и правильными заголовками."""
    response = make_csv_response("тест;данные", "test.csv")
    assert response.mimetype == "text/csv"
    assert "charset=utf-8" in response.content_type
    assert "attachment" in response.headers["Content-Disposition"]
    assert response.data.startswith(b"\xef\xbb\xbf")