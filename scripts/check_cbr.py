"""Проверка парсинга курсов ЦБ РФ через Playwright.

Запуск:
    python scripts/check_cbr.py

Проверяет, что Playwright установлен, Chromium скачан, селекторы ЦБ
актуальны, и модуль scrape_cbr_rates возвращает данные.
Полезно при деплое или дебаге.
"""

import asyncio
import sys
from pathlib import Path

# Корень проекта в sys.path — чтобы работал импорт `from app...`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.integrations.cbr_scraper import scrape_cbr_rates  # noqa: E402


async def main() -> int:
    print("Запускаю парсинг ЦБ РФ...")
    rates = await scrape_cbr_rates()

    if not rates:
        print("❌ Курсы не получены.")
        print("   Проверь: playwright install chromium, доступ к cbr.ru")
        return 1

    print(f"✅ Получено курсов: {len(rates)}")
    print()
    print("Примеры (первые 5):")
    for r in rates[:5]:
        print(f"  {r.code:4} {r.nominal:>4} = {r.rate:>10} руб.  ({r.rate_date})")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
