from urllib.parse import urljoin, urlparse

from flask import Response, redirect, request


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


def is_safe_url(target: str | None) -> bool:
    """
    Проверяет, что URL ведёт на тот же хост — защита от Open Redirect.
    """
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


def get_next_url(default: str) -> str:
    """
    Возвращает безопасный URL для redirect-back из query string 'next'.
    Если 'next' нет или он небезопасен — возвращает default.
    """
    candidate = request.args.get("next")
    if candidate and is_safe_url(candidate):
        return candidate
    return default


def safe_redirect(default_url: str):
    """
    Redirect на 'next' из формы или query string, если он безопасен.
    Иначе — на default_url.
    """
    candidate = request.form.get("next") or request.args.get("next")
    if candidate and is_safe_url(candidate):
        return redirect(candidate)
    return redirect(default_url)
