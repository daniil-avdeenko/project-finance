"""
Актуальные курсы валют ЦБ РФ.

Источник — таблица currency_rates, которая обновляется job_scrape_cbr
(Playwright, каждые 6 часов). Возвращает последний доступный курс.
"""

from flask import jsonify

from app.api.v1 import api_v1_bp
from app.services.currency_service import get_rates_map


@api_v1_bp.route("/currencies", methods=["GET"])
def api_currencies():
    """
    Актуальные курсы валют.

    Возвращает USD и EUR на последнюю доступную дату.
    Пустой объект — если курсы ещё не подгружены (первый запуск).
    """
    rates = get_rates_map({"USD", "EUR"})

    result = {}
    for code, rate_list in rates.items():
        if not rate_list:
            continue
        r = rate_list[0]  # самый свежий — благодаря order_by desc
        result[code] = {
            "code": r.code,
            "rate_date": r.rate_date.isoformat(),
            "nominal": r.nominal,
            "rate_rub": r.rate_rub,
        }

    return jsonify({"rates": result})
