"""
Сервис работы с курсами валют: сохранение в БД + конвертация.

Курсы пишутся из job_scrape_cbr (Playwright → БД).
get_rates_map кэширует результат в Redis (TTL 5 минут),
если Redis доступен — иначе работает напрямую с БД.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from sqlalchemy import select

from app import db
from app.cache import get_cache
from app.models import CurrencyRate

logger = logging.getLogger(__name__)

BASE_CURRENCY = "RUB"
RATES_CACHE_TTL = timedelta(hours=1)
RATES_CACHE_PREFIX = "rates_map:"


@dataclass(frozen=True)
class CachedRate:
    """
    Лёгкая копия CurrencyRate для кэша.
    """

    code: str
    rate_date: date
    nominal: int
    rate_rub: float


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

    Прямой запрос в БД, без кэша. Используется в convert_to_rub (для property
    Transaction.amount_rub), где кэширование на уровне одной транзакции не окупается.
    Если on_date=None — берётся последний доступный курс.
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

    return round(amount * rate.rate_rub / rate.nominal, 2)


def get_rates_map(codes: set[str]) -> dict[str, list[CachedRate]]:
    """
    Загружает все курсы для указанных кодов.

    Сначала проверяет кэш Redis (TTL 5 минут). При промахе делает SQL-запрос
    и сохраняет результат. При отсутствии Redis работает напрямую с БД.

    Возвращает {code: [CachedRate, ...]}, отсортированные по rate_date desc.
    """
    codes = {c for c in codes if c and c != BASE_CURRENCY}
    if not codes:
        return {}

    cache_key = RATES_CACHE_PREFIX + ",".join(sorted(codes))
    cache = get_cache()

    if cache:
        try:
            cached = cache.get(cache_key)
            if cached:
                parsed = json.loads(cached)
                return {
                    code: [
                        CachedRate(
                            code=r["code"],
                            rate_date=date.fromisoformat(r["rate_date"]),
                            nominal=r["nominal"],
                            rate_rub=r["rate_rub"],
                        )
                        for r in rates
                    ]
                    for code, rates in parsed.items()
                }
        except Exception as e:
            logger.warning("Ошибка чтения из Redis (%s): %s", cache_key, e)

    stmt = (
        select(CurrencyRate)
        .where(CurrencyRate.code.in_(codes))
        .order_by(CurrencyRate.code, CurrencyRate.rate_date.desc())
    )

    result: dict[str, list[CachedRate]] = {}
    for rate in db.session.execute(stmt).scalars():
        result.setdefault(rate.code, []).append(
            CachedRate(
                code=rate.code,
                rate_date=rate.rate_date,
                nominal=rate.nominal,
                rate_rub=rate.rate_rub,
            )
        )

    if cache and result:
        try:
            serialized = {code: [asdict(r) for r in rates] for code, rates in result.items()}
            cache.setex(
                cache_key,
                RATES_CACHE_TTL,
                json.dumps(serialized, default=str),
            )
        except Exception as e:
            logger.warning("Ошибка записи в Redis (%s): %s", cache_key, e)

    return result


def get_latest_rates(codes: set[str]) -> list[CachedRate]:
    """
    Возвращает последний доступный курс для каждого из кодов.
    """
    rates_map = get_rates_map(codes)
    return [rates_map[code][0] for code in sorted(rates_map) if rates_map[code]]


def convert_with_rates(
    amount: float,
    currency: str,
    on_date: date | None,
    rates_map: dict[str, list[CachedRate]],
) -> float:
    """
    Конвертирует сумму в RUB, используя предзагруженный rates_map.

    Без SQL-запросов — все данные уже в памяти или в кэше.
    """
    if not currency or currency == BASE_CURRENCY:
        return amount

    rates = rates_map.get(currency, [])
    if not rates:
        logger.warning("Курс %s не найден в кеше", currency)
        return amount

    rate: CachedRate | None = None
    if on_date is None:
        rate = rates[0]
    else:
        for r in rates:
            if r.rate_date <= on_date:
                rate = r
                break

    if rate is None:
        logger.warning("Курс %s на %s не найден в кеше", currency, on_date)
        return amount

    return round(amount * rate.rate_rub / rate.nominal, 2)
