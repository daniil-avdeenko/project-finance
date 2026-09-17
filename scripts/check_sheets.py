"""Проверка подключения к Google Sheets API."""

import os
import sys
from pathlib import Path

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def check_connection() -> bool:
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")

    if not Path(creds_path).exists():
        print(f"❌ Файл {creds_path} не найден")
        return False
    if not spreadsheet_id:
        print("❌ GOOGLE_SPREADSHEET_ID не задан в .env")
        return False

    try:
        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.sheet1

        worksheet.update([["Соединение установлено!"], ["Запись в таблицу работает"]], "A1")

        print("✅ Успех!")
        print(f"   Таблица: {spreadsheet.title}")
        print(f"   Лист:    {worksheet.title}")
        print(f"   URL:     {spreadsheet.url}")
        return True
    except gspread.exceptions.SpreadsheetNotFound:
        print("❌ Таблица не найдена.")
        print("   Проверь: ID верный? Расшарена на email сервисного аккаунта?")
        return False
    except Exception as e:
        print(f"❌ Ошибка: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    sys.exit(0 if check_connection() else 1)
