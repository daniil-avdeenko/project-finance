import os

from grist_api import GristDocAPI


def get_grist_api():
    """Инициализирует и возвращает клиент Grist API."""
    api_key = os.getenv("GRIST_API_KEY")
    doc_id = os.getenv("GRIST_DOC_ID")
    server = os.getenv("GRIST_SERVER", "https://docs.getgrist.com")

    if not api_key:
        raise ValueError("Переменная окружения GRIST_API_KEY не установлена.")
    if not doc_id:
        raise ValueError("Переменная окружения GRIST_DOC_ID не установлена.")

    # Библиотека grist-api автоматически использует переменную окружения GRIST_API_KEY,
    # если она установлена, но мы передадим ее явно для ясности.
    os.environ["GRIST_API_KEY"] = api_key
    return GristDocAPI(doc_id, server=server)


def sync_projects_to_grist(projects):
    """Синхронизирует проекты из БД в Grist."""
    api = get_grist_api()

    # Преобразуем модели SQLAlchemy в список словарей
    rows_to_add = []
    for p in projects:
        rows_to_add.append(
            {
                "ID2": p.id,
                "A": p.name,
                "B": p.description or "",
                "C": p.total_income,
                "D": p.total_expense,
                "E": p.profit,
                "F": p.profitability,
            }
        )

    if not rows_to_add:
        print("Нет проектов для синхронизации.")
        return

    # Важно: для простоты примера мы просто добавляем записи.
    # В реальном приложении вы бы использовали метод upsert для обновления существующих.
    # Для этого нужно сначала получить записи, а затем решить, что делать.
    # Но для pet-проекта логика "добавить все" тоже сгодится.
    try:
        # В grist-api нет прямого upsert, нужно сначала удалить, потом добавить
        # или использовать сложную логику. Для простоты добавим.
        api.add_records("Projects", rows_to_add)
        print(f"Добавлено {len(rows_to_add)} проектов в Grist.")
    except Exception as e:
        print(f"Ошибка при синхронизации проектов: {e}")


def sync_transactions_to_grist(transactions):
    """Синхронизирует транзакции из БД в Grist."""
    api = get_grist_api()

    rows_to_add = []
    for t in transactions:
        rows_to_add.append(
            {
                "ID2": t.id,
                "A": t.date.strftime("%Y-%m-%dT%H:%M:%S"),
                "ID_": t.project_id,
                "B": t.project.name,
                "C": t.type,
                "D": t.amount,
                "E": t.description or "",
            }
        )

    if not rows_to_add:
        print("Нет транзакций для синхронизации.")
        return

    try:
        api.add_records("Transactions", rows_to_add)
        print(f"Добавлено {len(rows_to_add)} транзакций в Grist.")
    except Exception as e:
        print(f"Ошибка при синхронизации транзакций: {e}")
