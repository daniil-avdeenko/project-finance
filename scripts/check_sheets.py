"""Проверка подключения к Google Sheets API."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Корень проекта в sys.path — чтобы импортировать app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.integrations.google_sheets import get_client  # noqa: E402

load_dotenv()


def check_connection() -> bool:
    creds_present = bool(
        os.getenv("GOOGLE_CREDENTIALS_B64", "").strip()
        or Path(os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")).exists()
    )
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")

    if not creds_present:
        print("❌ Нет GOOGLE_CREDENTIALS_B64 и нет файла credentials.json")
        return False
    if not spreadsheet_id:
        print("❌ GOOGLE_SPREADSHEET_ID не задан в .env")
        return False

    try:
        client = get_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.sheet1

        worksheet.update([["Привет от Python!"], ["Соединение работает."]], "A1")

        print("✅ Успех!")
        print(f"   Таблица: {spreadsheet.title}")
        print(f"   Лист:    {worksheet.title}")
        print(f"   URL:     {spreadsheet.url}")
        return True
    except Exception as e:
        print(f"❌ Ошибка: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    sys.exit(0 if check_connection() else 1)
