"""
Сервис работы с курсами валют: сохранение в БД + конвертация.

КУрсы пишутся из job_scrape_cbr (Playwright → БД → Grist).
"""

import logging
from datetime import date

from sqlalchemy import select

from app import db
from app.models import CurrencyRate

logger = logging.getLogger(__name__)

BASE_CURRENCY = "RUB"


def upsert_rates(rates: list) -> dict[str, int]:
    """
    Сохраняет курсы в БД через upsert по (code, rate_date).

    rates — список ScrapedRate (code, nominal, rate, rate_date).
    Возвращает {'added': N, 'updated': M}.
    """
    added = 0
    updated = 0

    for r in rates:
        existing = db.session.execute(
            select(CurrencyRate).where(
                CurrencyRate.code == r.code,
                CurrencyRate.rate_date == r.rate_date,
            )
        ).scalar_one_or_none()

        if existing:
            existing.nominal = r.nominal
            existing.rate_rub = r.rate
            updated += 1
        else:
            db.session.add(
                CurrencyRate(
                    code=r.code,
                    rate_date=r.rate_date,
                    nominal=r.nominal,
                    rate_rub=r.rate,
                )
            )
            added += 1

    db.session.commit()
    logger.info("CurrencyRate: added=%d, updated=%d", added, updated)
    return {"added": added, "updated": updated}


def get_rate(code: str, on_date: date | None = None) -> CurrencyRate | None:
    """
    Возвращает курс валюты на дату или ближайшую предыдущую.

    Если on_date=None — берётся последний доступный курс.
    Возвращает None, если курса нет вообще (например, для RUB).
    """
    if on_date is None:
        stmt = (
            select(CurrencyRate)
            .where(CurrencyRate.code == code)
            .order_by(CurrencyRate.rate_date.desc())
            .limit(1)
        )
    else:
        stmt = (
            select(CurrencyRate)
            .where(CurrencyRate.code == code, CurrencyRate.rate_date <= on_date)
            .order_by(CurrencyRate.rate_date.desc())
            .limit(1)
        )

    return db.session.execute(stmt).scalar_one_or_none()


def convert_to_rub(amount: float, currency: str, on_date: date | None = None) -> float:
    """
    Конвертирует сумму из валюты в рубли по курсу ЦБ.
    """
    if not currency or currency == BASE_CURRENCY:
        return amount

    rate = get_rate(currency, on_date)
    if rate is None:
        logger.warning("Курс %s на %s не найден — сумма не сконвертирована", currency, on_date)
        return amount

    # rate_rub указан за `nominal` единиц
    return round(amount * rate.rate_rub / rate.nominal, 2)
