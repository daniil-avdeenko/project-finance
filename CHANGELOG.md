# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).
Проект использует [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

## [1.0.0] — 2026-10-23

Первый стабильный релиз.

### Возможности

- CRUD проектов, сотрудников (роли на проектах), категорий и транзакций.
- Дашборд с аналитикой рентабельности за период.
- Мультивалютность: RUB / USD / EUR / CNY, конвертация по курсу ЦБ на дату транзакции.
- Парсинг курсов ЦБ через Playwright с обходом DDoS-Guard.
- Экспорт в CSV / XLSX (openpyxl), синхронизация с Google Sheets с валидацией полей и retry.
- Event-driven уведомления в Telegram через `event_log` и отдельный процесс-планировщик.
- Публичный REST API `/api/v1/*` — потребляется внешним Telegram-агентом.
- Ручная синхронизация из UI с отображением статуса.
- Кэш Redis для курсов и категорий (TTL 1 час, инвалидация при обновлении).
- Адаптивная вёрстка: десктоп 125–250% браузерного зума, мобильные 360–375px.

### Инфраструктура

- Docker Compose (dev + prod), PostgreSQL 16, Redis 7.
- Два VPS: NL (приложение) + RU-прокси (доступ из РФ без VPN).
- Nginx + Let's Encrypt на обоих серверах.
- GitHub Actions: 3 CI-джоба, Deploy Preview на PR (GitHub-hosted), Deploy prod на self-hosted runner после merge в `main`.
- Redis + graceful degradation при недоступности.
- Rate limit на логин через Redis (Flask-Limiter, storage `redis://`), с fallback на `memory://` при недоступности Redis на старте и `swallow_errors=True` в рантайме.
- Разделение web и scheduler в два контейнера — без дублирования фоновых задач.
- Развязка сервисов через HTTP API — без shared-credentials к БД.

### Качество

- 283 теста, покрытие 88%.
- ruff, mypy, pre-commit, gitleaks.
- Conventional Commits, feature-ветки, branch protection, pre-push hook.
- `pip-tools` — раздельные lock-файлы для prod и dev, компиляция в Linux-контейнере.

### Известные ограничения

- `GIGACHAT_VERIFY_SSL=false` в production.
- Rate limit на логин: fallback на memory при недоступности Redis на старте, `swallow_errors=True` при падении в рантайме.
- CSP с `'unsafe-inline'` для совместимости с Bootstrap и inline-скриптами.
- HSTS — в бэклоге.
- Автоматические бэкапы PostgreSQL — в бэклоге.
