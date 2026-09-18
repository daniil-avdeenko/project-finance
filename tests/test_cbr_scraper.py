"""Тесты парсинга курсов ЦБ."""

import dataclasses
from datetime import date

import pytest

from app.integrations.cbr_scraper import (
    _cells_to_rate,
    _parse_nominal,
    _parse_rate,
    scrape_cbr_rates,
)

# ============================================================
#   _parse_rate
# ============================================================


def test_parse_rate_with_comma():
    assert _parse_rate("60,0692") == 60.0692


def test_parse_rate_with_spaces():
    assert _parse_rate("1 234,56") == 1234.56


def test_parse_rate_invalid():
    assert _parse_rate("abc") is None


def test_parse_rate_empty():
    assert _parse_rate("") is None


# ============================================================
#   _parse_nominal
# ============================================================


def test_parse_nominal_simple():
    assert _parse_nominal("100") == 100


def test_parse_nominal_with_space():
    assert _parse_nominal("1 000") == 1000


def test_parse_nominal_invalid():
    assert _parse_nominal("abc") is None


def test_parse_nominal_empty():
    assert _parse_nominal("") is None


# ============================================================
#   _cells_to_rate
# ============================================================


def test_cells_to_rate_valid():
    cells = ["036", "AUD", "1", "Австралийский доллар", "60,0692"]
    result = _cells_to_rate(cells, date(2026, 9, 18))

    assert result is not None
    assert result.code == "AUD"
    assert result.nominal == 1
    assert result.rate == 60.0692
    assert result.rate_date == date(2026, 9, 18)


def test_cells_to_rate_short_row():
    """Меньше 5 ячеек → None."""
    assert _cells_to_rate(["036", "AUD"], date(2026, 9, 18)) is None


def test_cells_to_rate_empty_code():
    cells = ["036", "", "1", "Валюта", "60,0692"]
    assert _cells_to_rate(cells, date(2026, 9, 18)) is None


def test_cells_to_rate_bad_rate():
    cells = ["036", "AUD", "1", "Валюта", "not-a-number"]
    assert _cells_to_rate(cells, date(2026, 9, 18)) is None


def test_cells_to_rate_frozen_dataclass():
    """ScrapedRate иммутабельный — попытка изменить поле падает."""
    cells = ["036", "AUD", "1", "Австралийский доллар", "60,0692"]
    result = _cells_to_rate(cells, date(2026, 9, 18))
    assert result is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.code = "USD"  # type: ignore[misc]


# ============================================================
#   scrape_cbr_rates — ошибка Playwright
# ============================================================


async def test_scrape_cbr_rates_returns_empty_on_playwright_error(monkeypatch):
    """Если Playwright падает — возвращается пустой список, не исключение."""
    from app.integrations import cbr_scraper

    class BrokenPlaywright:
        async def __aenter__(self):
            raise RuntimeError("Playwright not available")

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(cbr_scraper, "async_playwright", BrokenPlaywright)

    rates = await scrape_cbr_rates()

    assert rates == []


# ============================================================
#   scrape_cbr_rates — полный flow с мок-Playwright
# ============================================================


class _FakeRow:
    """Имитация строки таблицы: возвращает ячейки в нужном порядке."""

    def __init__(self, cells: list[str]):
        self._cells = cells

    def locator(self, _selector: str):
        return self

    async def all_text_contents(self) -> list[str]:
        return self._cells


class _FakePage:
    def __init__(self, rows: list[_FakeRow]):
        self._rows = rows
        self.goto_called = False
        self.selector_waited = False

    async def goto(self, url: str, **_kwargs) -> None:
        self.goto_called = True
        assert url.startswith("https://www.cbr.ru/")

    async def wait_for_selector(self, selector: str, **_kwargs) -> None:
        self.selector_waited = True
        assert selector == "table.data"

    def locator(self, _selector: str):
        return self

    async def all(self) -> list[_FakeRow]:
        return self._rows


class _FakeBrowser:
    def __init__(self, page: _FakePage):
        self._page = page
        self.closed = False

    async def new_page(self) -> _FakePage:
        return self._page

    async def close(self) -> None:
        self.closed = True


class _FakePlaywrightManager:
    """Имитация `async with async_playwright() as p`."""

    def __init__(self, browser: _FakeBrowser):
        self._browser = browser

    @property
    def chromium(self):
        """Как в реальном Playwright — атрибут, а не метод."""
        return self

    async def launch(self, **_kwargs) -> _FakeBrowser:
        return self._browser

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


async def test_scrape_cbr_rates_full_flow(monkeypatch):
    """Полный успешный flow: 3 валидные строки + 2 мусорных."""
    from app.integrations import cbr_scraper

    rows = [
        _FakeRow(["036", "AUD", "1", "Австралийский доллар", "60,0692"]),
        _FakeRow(["840", "USD", "1", "Доллар США", "84,5093"]),
        _FakeRow(["978", "EUR", "1", "Евро", "97,4984"]),
        _FakeRow(["999", "", "1", "Пустая валюта", "10,0"]),  # мусор — пропустится
        _FakeRow(["001", "JPY"]),  # короткая — пропустится
    ]
    page = _FakePage(rows)
    browser = _FakeBrowser(page)
    manager = _FakePlaywrightManager(browser)

    monkeypatch.setattr(cbr_scraper, "async_playwright", lambda: manager)

    rates = await scrape_cbr_rates()

    # 3 валидных строки попали, мусорные — нет
    assert len(rates) == 3
    assert [r.code for r in rates] == ["AUD", "USD", "EUR"]
    assert rates[1].rate == 84.5093

    # Браузер закрылся даже при успехе (finally)
    assert browser.closed
    assert page.goto_called
    assert page.selector_waited


async def test_scrape_cbr_rates_closes_browser_on_parse_error(monkeypatch):
    """Если парсинг ячеек падает — браузер всё равно закрывается."""

    class ExplodingRow:
        def locator(self, _s):
            return self

        async def all_text_contents(self):
            raise RuntimeError("DOM broke")

    from app.integrations import cbr_scraper

    page = _FakePage([ExplodingRow()])
    browser = _FakeBrowser(page)
    manager = _FakePlaywrightManager(browser)

    monkeypatch.setattr(cbr_scraper, "async_playwright", lambda: manager)

    rates = await scrape_cbr_rates()

    assert rates == []
    assert browser.closed  # finally сработал
