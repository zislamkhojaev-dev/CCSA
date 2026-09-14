# Документация CCSA

Сервис речевой аналитики для контакт-центра (CCSA): загрузка звонков, распознавание речи (ASR), оценка качества через LLM, **исследования (метаанализ)**, дашборды и плейграунд для тестов.

## Содержание

| Документ | Описание |
|----------|----------|
| [Установка и запуск](installation.md) | Docker, первый запуск, миграции, вход в систему |
| [Журнал изменений](changelog.md) | Production readiness, контракт API, миграции |
| [Архитектура](architecture.md) | Сервисы, потоки данных, компоненты |
| [Конфигурация](configuration.md) | `.env`, настройки в UI, ASR, LLM, автоматизация |
| [Пайплайн обработки](pipeline.md) | От звонка до оценки: Webitel → STT → LLM |
| [Исследования (метаанализ)](research.md) | LLM-отчёт по выборке звонков: промпт, фильтры, API |
| [Руководство пользователя](user-guide.md) | Разделы интерфейса: дашборд, звонки, сценарии, исследования, плейграунд |
| [Дизайн-система UI](design-system.md) | Токены, темы, компоненты (Cursor-style flat UI) |
| [Дашборды: внешний вид](dashboard-visual.md) | Визуальный язык дашбордов (по референсам) |
| [Дашборды: состав](dashboard-composition.md) | Метрики и визуализация для руководителя КЦ |
| [Коды ошибок](error-codes.md) | Error Codes Matrix, `trace_id` |
| [API](api.md) | REST endpoints, аутентификация |
| [Разработка](development.md) | Локальная разработка, тесты, миграции |
| [Устранение неполадок](troubleshooting.md) | ASR, таймауты, Redis, типичные ошибки |

## Быстрые ссылки

- **Интерфейс:** http://localhost:8080 (логин задаётся при сиде, не хранится в UI)
- **API (OpenAPI):** http://localhost:8000/docs (напрямую к контейнеру `api`)
- **STT:** только внутренняя docker-сеть (`stt-service:8001`), не публикуется на хост
- **Модели ASR:** [models/README.md](../models/README.md)

## Стек (кратко)

- Backend: FastAPI, SQLAlchemy, Alembic, Celery, Redis
- STT: faster-whisper (INT8), опционально Pyannote
- Storage: PostgreSQL, MinIO
- Frontend: React 18, TypeScript, Vite
- Proxy: nginx
