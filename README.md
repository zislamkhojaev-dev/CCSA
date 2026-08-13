# CCSA — Сервис речевой аналитики для контакт-центра

Платформа речевой аналитики для колл-центра: загрузка и хранение звонков, распознавание речи (узбекский ASR), оценка качества через LLM, **исследования (метаанализ по выборке звонков)**, настраиваемые дашборды, сценарии оценки и плейграунд для тестов.

## Возможности

- **Ingestion:** Webitel API → MinIO → очередь обработки
- **STT:** Faster-Whisper INT8, диаризация (стерео-каналы / Pyannote / моно)
- **LLM:** OpenAI, Gemini, Ollama — оценка по сценарию с JSON Schema, маскирование PII
- **Исследования:** сводный LLM-отчёт по выборке транскрибированных звонков (промпт + фильтры)
- **UI:** дашборд-конструктор, звонки, операторы, сценарии, исследования, плейграунд, настройки

## Документация

Полная документация в каталоге **[docs/](docs/README.md)**:

- [Установка и запуск](docs/installation.md)
- [Архитектура](docs/architecture.md)
- [Конфигурация](docs/configuration.md)
- [Пайплайн обработки](docs/pipeline.md)
- [Исследования (метаанализ)](docs/research.md)
- [Руководство пользователя](docs/user-guide.md)
- [API](docs/api.md)
- [Разработка](docs/development.md)
- [Устранение неполадок](docs/troubleshooting.md)

## Быстрый старт

```bash
cp .env.example .env
make init
```

Откройте **http://localhost:8080** — логин `admin` / `admin123`.

Модель ASR: [models/README.md](models/README.md).

## Стек

| Слой | Технологии |
|------|------------|
| API | FastAPI, SQLAlchemy, Alembic |
| Очереди | Celery, Redis |
| STT | faster-whisper (CT2), отдельный сервис |
| БД / файлы | PostgreSQL, MinIO |
| UI | React 18, TypeScript, Vite |
| Прокси | nginx |

## Сервисы (Docker)

| Сервис | Порт | Описание |
|--------|------|----------|
| nginx | 8080 | Единая точка входа |
| api | 8000 (internal) | REST API |
| stt-service | 8001 | ASR |
| frontend | — | React SPA |
| postgres, redis, minio | — | Инфраструктура |
| celery-worker | — | LLM + I/O очереди |
| celery-worker-stt | — | Очередь ASR (`concurrency=1`) |
| celery-beat | — | Расписание |

## GPU для STT

```bash
make gpu-up
# или: docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d stt-service
```

## Тесты

```bash
make test
```

## Переменные окружения

См. [.env.example](.env.example) и [docs/configuration.md](docs/configuration.md).
