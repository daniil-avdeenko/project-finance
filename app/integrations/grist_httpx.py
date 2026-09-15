import logging
import os

import httpx

logger = logging.getLogger(__name__)


class GristClient:
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
        url = f"{self.base_url}/{endpoint}"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method=method, url=url, headers=self.headers, timeout=30.0, **kwargs
                )
                response.raise_for_status()
                if response.status_code == 204:
                    return {}
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(
                    "HTTP ошибка при запросе %s %s: %s — %s",
                    method,
                    url,
                    e.response.status_code,
                    e.response.text,
                )
                raise
            except httpx.RequestError as e:
                logger.error("Ошибка сети при запросе %s %s: %s", method, url, e)
                raise

    async def upsert_records(self, table_id: str, records: list[dict]) -> dict:
        """Upsert записей. Возвращает только статистику."""
        payload = {"records": records}
        response = await self._request("PUT", f"tables/{table_id}/records", json=payload)
        return {
            "added": len(response.get("addRecordIds", [])),
            "updated": len(response.get("updateRecordIds", [])),
        }


async def sync_projects_to_grist_httpx(projects: list) -> dict:
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

    if not records:
        logger.info("Нет проектов для синхронизации.")
        return {"added": 0, "updated": 0}

    result = await client.upsert_records("Projects", records)
    logger.info("Проекты: добавлено %d, обновлено %d", result["added"], result["updated"])
    return result


async def sync_transactions_to_grist_httpx(transactions: list) -> dict:
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
            },
        }
        for t in transactions
    ]

    if not records:
        logger.info("Нет транзакций для синхронизации.")
        return {"added": 0, "updated": 0}

    result = await client.upsert_records("Transactions", records)
    logger.info("Транзакции: добавлено %d, обновлено %d", result["added"], result["updated"])
    return result
