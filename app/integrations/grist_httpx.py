import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)


class GristClient:
    """Асинхронный клиент Grist API с retry и chunking."""

    MAX_RETRIES = 3
    BACKOFF_BASE = 1.0  # секунды; в тестах переопределяем на маленькое
    CHUNK_SIZE = 100  # максимум записей в одном PUT

    def __init__(self, api_key: str, doc_id: str, server: str = "https://docs.getgrist.com"):
        self.api_key = api_key
        self.doc_id = doc_id
        self.server = server.rstrip("/")
        self.base_url = f"{self.server}/api/docs/{self.doc_id}"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(self, method: str, endpoint: str, **kwargs):
        """
        HTTP-запрос с retry для сетевых ошибок.

        - 4xx/5xx — поднимаем HTTPStatusError без retry
        - httpx.RequestError (ReadError, ConnectError, Timeout) — retry с backoff

        AsyncClient создаётся один раз на весь метод — retry переиспользует
        пул соединений.
        """
        url = f"{self.base_url}/{endpoint}"
        last_exc: httpx.RequestError | None = None

        async with httpx.AsyncClient() as client:
            for attempt in range(1, self.MAX_RETRIES + 1):
                try:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=self.headers,
                        timeout=30.0,
                        **kwargs,
                    )
                    response.raise_for_status()
                    if response.status_code == 204 or not response.content:
                        return {}
                    return response.json()

                except httpx.HTTPStatusError as e:
                    logger.error(
                        "HTTP %d при %s %s: %s",
                        e.response.status_code,
                        method,
                        url,
                        e.response.text[:500],
                    )
                    raise

                except httpx.RequestError as e:
                    last_exc = e
                    if attempt < self.MAX_RETRIES:
                        delay = self.BACKOFF_BASE * (2 ** (attempt - 1))
                        logger.warning(
                            "Сетевая ошибка при %s %s (попытка %d/%d): %s — %r. "
                            "Повтор через %.1fс",
                            method,
                            url,
                            attempt,
                            self.MAX_RETRIES,
                            type(e).__name__,
                            e,
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "Сетевая ошибка при %s %s после %d попыток: %s — %r",
                            method,
                            url,
                            self.MAX_RETRIES,
                            type(e).__name__,
                            e,
                        )
                        raise

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Retry loop exited without result or exception")

    async def upsert_records(self, table_id: str, records: list[dict]) -> dict:
        """
        Upsert записей чанками по CHUNK_SIZE.

        Режем на чанки по 100 и агрегируем
        статистику.
        При ошибке в любом чанке — raise наверх, остальные не отправляем.
        """
        if not records:
            return {"added": 0, "updated": 0}

        total_added = 0
        total_updated = 0
        total_chunks = (len(records) + self.CHUNK_SIZE - 1) // self.CHUNK_SIZE

        for i in range(0, len(records), self.CHUNK_SIZE):
            chunk = records[i : i + self.CHUNK_SIZE]
            chunk_num = i // self.CHUNK_SIZE + 1

            logger.debug(
                "Upsert %s: чанк %d/%d, записей %d",
                table_id,
                chunk_num,
                total_chunks,
                len(chunk),
            )

            payload = {"records": chunk}
            response = await self._request("PUT", f"tables/{table_id}/records", json=payload)

            total_added += len(response.get("addRecordIds", []))
            total_updated += len(response.get("updateRecordIds", []))

        logger.info(
            "Upsert %s: %d чанков, added=%d, updated=%d",
            table_id,
            total_chunks,
            total_added,
            total_updated,
        )
        return {"added": total_added, "updated": total_updated}

    async def prune_missing_records(self, table_id: str, keep_ids: set) -> int:
        """
        Удаляет из Grist записи, чьи ID2 отсутствуют в keep_ids.

        Нужно, потому что PUT /records делает upsert — обновляет и добавляет,
        но не удаляет. Без prune soft-deleted записи копятся в Grist навсегда.

        keep_ids — множество ID2, которые должны остаться. Например,
        {p.id for p in projects} для активных проектов.

        Возвращает число удалённых записей.
        """
        # 1. Получить все записи таблицы
        data = await self._request("GET", f"tables/{table_id}/records")
        all_records = data.get("records", [])

        if not all_records:
            return 0

        # 2. Найти сироты — записи, чьи ID2 не входят в keep_ids
        orphans: list[int] = []
        for rec in all_records:
            fields = rec.get("fields", {})
            our_id = fields.get("ID2")
            if our_id not in keep_ids:
                orphans.append(rec["id"])  # внутренний Grist ID

        if not orphans:
            logger.debug("Prune %s: сирот нет", table_id)
            return 0

        # 3. Удалить пачкой
        await self._request(
            "POST",
            f"tables/{table_id}/records/delete",
            json=orphans,
        )
        logger.info("Prune %s: удалено %d записей", table_id, len(orphans))
        return len(orphans)


async def sync_projects_to_grist_httpx(projects: list, prune: bool = True) -> dict:
    """
    Синхронизирует проекты с Grist.

    prune=True — удаляет из Grist проекты, которых нет в БД (soft-deleted).
    prune=False — только upsert, без удаления.
    """
    api_key = os.getenv("GRIST_API_KEY")
    doc_id = os.getenv("GRIST_DOC_ID")
    server = os.getenv("GRIST_SERVER", "https://docs.getgrist.com")

    if not api_key or not doc_id:
        raise ValueError("GRIST_API_KEY и GRIST_DOC_ID должны быть установлены.")

    client = GristClient(api_key=api_key, doc_id=doc_id, server=server)

    records = [
        {
            "require": {"ID2": p.id},
            "fields": {
                "A": p.name,
                "B": p.description or "",
                "C": p.total_income,
                "D": p.total_expense,
                "E": p.profit,
                "F": p.profitability,
            },
        }
        for p in projects
    ]

    result = {"added": 0, "updated": 0, "deleted": 0}

    if records:
        upsert_result = await client.upsert_records("Projects", records)
        result["added"] = upsert_result["added"]
        result["updated"] = upsert_result["updated"]

    if prune:
        keep_ids = {p.id for p in projects}
        result["deleted"] = await client.prune_missing_records("Projects", keep_ids)

    logger.info(
        "Проекты: добавлено %d, обновлено %d, удалено %d",
        result["added"],
        result["updated"],
        result["deleted"],
    )
    return result


async def sync_transactions_to_grist_httpx(transactions: list, prune: bool = True) -> dict:
    """
    Синхронизирует транзакции с Grist.

    prune=True — удаляет из Grist транзакции, которых нет в БД.
    """
    api_key = os.getenv("GRIST_API_KEY")
    doc_id = os.getenv("GRIST_DOC_ID")
    server = os.getenv("GRIST_SERVER", "https://docs.getgrist.com")

    if not api_key or not doc_id:
        raise ValueError("GRIST_API_KEY и GRIST_DOC_ID должны быть установлены.")

    client = GristClient(api_key=api_key, doc_id=doc_id, server=server)

    records = [
        {
            "require": {"ID2": t.id},
            "fields": {
                "A": t.date.strftime("%Y-%m-%dT%H:%M:%S"),
                "ID_": t.project_id,
                "B": t.project.name,
                "C": t.type,
                "D": t.amount,
                "E": t.description or "",
                "F": t.currency or "RUB",
                "RUB_": t.amount_rub,
            },
        }
        for t in transactions
    ]

    result = {"added": 0, "updated": 0, "deleted": 0}

    if records:
        upsert_result = await client.upsert_records("Transactions", records)
        result["added"] = upsert_result["added"]
        result["updated"] = upsert_result["updated"]

    if prune:
        keep_ids = {t.id for t in transactions}
        result["deleted"] = await client.prune_missing_records("Transactions", keep_ids)

    logger.info(
        "Транзакции: добавлено %d, обновлено %d, удалено %d",
        result["added"],
        result["updated"],
        result["deleted"],
    )
    return result


async def sync_rates_to_grist_httpx(rates: list) -> dict:
    """
    Синхронизирует курсы валют в Grist (лист ExchangeRates).

    rates — список ScrapedRate. ID2 = код валюты (USD, EUR),
    повторный запуск обновляет курс, а не создаёт дубликат.
    """
    api_key = os.getenv("GRIST_API_KEY")
    doc_id = os.getenv("GRIST_DOC_ID")
    server = os.getenv("GRIST_SERVER", "https://docs.getgrist.com")

    if not api_key or not doc_id:
        raise ValueError("GRIST_API_KEY и GRIST_DOC_ID должны быть установлены.")

    client = GristClient(api_key=api_key, doc_id=doc_id, server=server)

    records = [
        {
            "require": {"ID2": r.code},
            "fields": {
                "A": r.rate_date.isoformat(),
                "B": r.code,
                "C": r.nominal,
                "D": r.rate,
            },
        }
        for r in rates
    ]

    if not records:
        logger.info("Нет курсов для синхронизации.")
        return {"added": 0, "updated": 0}

    result = await client.upsert_records("ExchangeRates", records)
    logger.info("Курсы: добавлено %d, обновлено %d", result["added"], result["updated"])
    return result
