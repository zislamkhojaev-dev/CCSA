# Установка и запуск

## Требования

- Docker и Docker Compose
- ~4 GB RAM для CPU-режима STT (больше при GPU)
- Каталог модели ASR: `models/OvozifyLabs--whisper-small-uz-v1-int8/` (см. [models/README.md](../models/README.md))

## Первый запуск

```bash
cp .env.example .env
# При необходимости: OPENAI_API_KEY, HF_TOKEN (для pyannote), WEBITEL_*

make init
```

`make init` выполняет: `docker compose build`, `up`, миграции Alembic, seed (админ и демо-сценарий).

Откройте **http://localhost:8080**

| Параметр | Значение по умолчанию |
|----------|------------------------|
| Логин | `admin` |
| Пароль | `admin123` |

## Команды Makefile

| Команда | Действие |
|---------|----------|
| `make up` | Запустить контейнеры |
| `make down` | Остановить |
| `make build` | Пересобрать образы |
| `make logs` | Логи всех сервисов |
| `make migrate` | `alembic upgrade head` |
| `make seed` | Начальные данные |
| `make test` | pytest в контейнере api |
| `make gpu-up` | STT с GPU (overlay compose) |
| `make convert-stt-model` | Конвертация Whisper → CT2 локально |

## Сервисы Docker

| Сервис | Порт (хост) | Назначение |
|--------|-------------|------------|
| nginx | 8080 | UI + прокси `/api` |
| api | — (8000 внутри) | REST API |
| frontend | — | React (dev server в контейнере) |
| postgres | — | БД платформы |
| redis | — | Celery, семафор ASR, SSE плейграунда |
| minio | — | Хранение аудио |
| stt-service | 8001 | Распознавание речи |
| celery-worker | — | LLM и I/O |
| celery-worker-stt | — | Распознавание (очередь `stt`) |
| celery-beat | — | Расписание (Webitel, очередь звонков) |

## Модель ASR

Перед первым запуском STT нужен каталог `models/OvozifyLabs--whisper-small-uz-v1-int8/` с файлом `model.bin`.

Если каталога нет:

```bash
make convert-stt-model
```

Проверка после старта:

```bash
curl -s http://localhost:8001/health | python3 -m json.tool
```

## Перезапуск после обновления кода

```bash
docker compose restart api celery-worker celery-worker-stt celery-beat stt-service
docker compose restart nginx frontend   # при изменении UI
```

После смены `CELERY_LLM_CONCURRENCY` в `.env`:

```bash
docker compose restart celery-worker celery-worker-stt
```

## Бэкап БД

```bash
docker compose exec postgres pg_dump -U ccsa ccsa > backup_$(date +%Y%m%d).sql
```

Аудио — volume `minio_data` или репликация MinIO.
