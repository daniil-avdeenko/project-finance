from flask import Response


def make_csv_response(csv_content, filename):
    """
    Возвращает Response с CSV-файлом в кодировке UTF-8 с BOM.
    """
    # Добавляем BOM для корректного отображения в Excel
    content = "\ufeff" + csv_content
    response = Response(content, mimetype="text/csv")
    response.headers.set("Content-Disposition", "attachment", filename=filename)
    return response


def parse_ids_from_string(ids_str):
    """
    Преобразует строку с ID (разделёнными запятыми) в список целых чисел.
    Игнорирует пустые и нечисловые значения.
    """
    if not ids_str:
        return []
    ids = []
    for part in ids_str.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids
