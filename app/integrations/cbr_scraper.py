"""
Парсинг курсов валют с сайта ЦБ РФ через Playwright.

Сайт ЦБ отдаёт HTML-таблицу без JSON API — Playwright здесь оправдан.
Запускается из scheduler'а (раз в 6 часов) или через CLI.
"""

import logging
from dataclasses import dataclass
from datetime import date

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

CBR_URL = "https://www.cbr.ru/currency_base/daily/"
TABLE_SELECTOR = "table.data"
ROW_SELECTOR = "table.data tbody tr"
PAGE_TIMEOUT_MS = 15000


@dataclass(frozen=True)
class ScrapedRate:
    """Одна строка из таблицы ЦБ."""

    code: str  # 'USD', 'EUR'
    nominal: int  # 1, 10, 100
    rate: float  # курс в рублях
    rate_date: date  # дата, к которой относится курс


def _parse_rate(raw: str) -> float | None:
    """Парсит курс из '60,0692' → 60.0692."""
    cleaned = raw.strip().replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_nominal(raw: str) -> int | None:
    """Парсит номинал из '100' → 100."""
    cleaned = raw.strip().replace(" ", "")
    try:
        return int(cleaned)
    except ValueError:
        return None


def _cells_to_rate(cells: list[str], target_date: date) -> ScrapedRate | None:
    """
    Преобразует одну строку таблицы ЦБ в ScrapedRate.

    Ожидаемый формат: [Цифр. код, Букв. код, Номинал, Название, Курс].
    Возвращает None, если строка невалидна (не тот формат, битые числа).
    """
    if len(cells) < 5:
        return None

    code = cells[1].strip()
    nominal = _parse_nominal(cells[2])
    rate = _parse_rate(cells[4])

    if not code or nominal is None or rate is None:
        return None

    return ScrapedRate(
        code=code,
        nominal=nominal,
        rate=rate,
        rate_date=target_date,
    )


async def scrape_cbr_rates(target_date: date | None = None) -> list[ScrapedRate]:
    """
    Открывает страницу ЦБ и парсит таблицу курсов.

    target_date — дата, к которой относятся курсы (по умолчанию сегодня).
    Возвращает список ScrapedRate. Пустой список при ошибке парсинга
    (например, если сайт изменил вёрстку) — не поднимает исключений наружу,
    только логирует.
    """
    if target_date is None:
        target_date = date.today()

    rates: list[ScrapedRate] = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            try:
                page = await browser.new_page(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    locale="ru-RU",
                    timezone_id="Europe/Moscow",
                )
                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', " "{get: () => undefined});"
                )
                await page.goto(CBR_URL, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
                await page.wait_for_selector(TABLE_SELECTOR, timeout=PAGE_TIMEOUT_MS)

                rows = await page.locator(ROW_SELECTOR).all()
                logger.info("Найдено строк в таблице ЦБ: %d", len(rows))

                for row in rows:
                    cells = await row.locator("td").all_text_contents()
                    parsed = _cells_to_rate([c.strip() for c in cells], target_date)
                    if parsed:
                        rates.append(parsed)
            finally:
                await browser.close()

    except PlaywrightTimeoutError as e:
        logger.error("Таймаут при загрузке страницы ЦБ: %s", e)
    except Exception as e:
        logger.exception("Ошибка парсинга ЦБ: %s", e)

    return rates
