# Конфигурация

## Файл `.env`

Скопируйте из `.env.example`. Основные группы переменных:

### Приложение

| Переменная | Описание |
|------------|----------|
| `SECRET_KEY` | Сессии FastAPI |
| `SETTINGS_ENCRYPTION_KEY` | Шифрование ключей в БД (Fernet) |
| `APP_ENV` | `development` / production |

### PostgreSQL

| Переменная | По умолчанию |
|------------|--------------|
| `POSTGRES_USER` | `ccsa` |
| `POSTGRES_PASSWORD` | `ccsa_secret` |
| `POSTGRES_DB` | `ccsa` |

### Redis / Celery

| Переменная | Описание |
|------------|----------|
| `REDIS_URL` | Кэш, семафор ASR, SSE |
| `CELERY_BROKER_URL` | Очередь задач |
| `CELERY_RESULT_BACKEND` | Результаты Celery |
| `CELERY_WORKER_CONCURRENCY` | Устарело: STT-воркер всегда `concurrency=1` |
| `CELERY_LLM_CONCURRENCY` | Параллельных LLM/I/O задач (по умолчанию 2; `restart celery-worker`) |

### MinIO

| Переменная | Описание |
|------------|----------|
| `MINIO_ENDPOINT` | `minio:9000` в Docker |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | Учётные данные |
| `MINIO_BUCKET` | `ccsa-audio` |

### STT (stt-service)

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `STT_MODEL` | `OvozifyLabs/whisper-small-uz-v1` | HF id или алиас |
| `STT_DEVICE` | `cpu` | `cuda` для GPU |
| `STT_COMPUTE_TYPE` | `int8` | Тип вычислений CT2 |
| `STT_DIARIZATION_METHOD` | `stereo_channels` | `stereo_channels` / `pyannote` / `mono` |
| `STT_LANGUAGE` | `uz` | Язык ASR |
| `STT_INITIAL_PROMPT` | — | Словарь КЦ для Whisper (бренды, типичные фразы) |
| `STT_CLIENT_CHANNEL` | `left` | Канал клиента в стерео (`left` / `right`) |
| `HF_TOKEN` | — | Для Pyannote (Hugging Face) |

Полный список STT-переменных — в `backend/stt/main.py` (`STT_BEAM_SIZE`, `STT_VAD_FILTER`, …).

### LLM

| Переменная | Описание |
|------------|----------|
| `OPENAI_API_KEY` | OpenAI |
| `OPENAI_MODEL` | Модель по умолчанию |

Дополнительные ключи (Gemini, Ollama) задаются в **Настройки → Модели и AI** (хранятся в БД в зашифрованном виде).

### Исследования (LLM метаанализ)

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `RESEARCH_MAX_CALLS` | `200` | Максимум звонков в одном исследовании |

Подробнее: [research.md](research.md).

### Webitel (опционально)

| Переменная | Описание |
|------------|----------|
| `WEBITEL_API_URL` | URL API |
| `WEBITEL_ACCESS_TOKEN` | Токен |

Также настраивается в UI: **Настройки → Коннекторы**.

---

## Настройки в интерфейсе

**Настройки → Модели и AI**

### ASR

- Провайдер: локальный STT / OpenAI Whisper API / другой API
- Модель (список uz-моделей)
- Метод диаризации (для локального STT)

### Производительность ASR

| Параметр | Рекомендация (CPU) | Эффект |
|----------|-------------------|--------|
| Макс. параллельных запросов к STT | `1` | Семафор Redis, защита от перегрузки STT |
| Таймаут HTTP к STT (сек) | `600`–`1200` | Ожидание ответа `/transcribe` |
| Плейграунд: по одному файлу | включено | Файлы обрабатываются последовательно |
| Параллельность Celery worker | `1` | + `CELERY_WORKER_CONCURRENCY` в `.env` и restart |

### LLM

- Провайдер: OpenAI / Gemini / Ollama
- Модель, API-ключи
- Анонимизация PII перед облачным LLM

**Настройки → Автоматизация**

- Размер пакета (`batch_size`) — сколько звонков ставить в очередь за цикл
- Дни и часы работы синхронизации
- Сценарий по умолчанию

**Настройки → Коннекторы**

- Webitel API и БД (для синхронизации операторов/звонков)

---

## Сценарии оценки

В **Сценарии и критерии** для каждого сценария:

- **Системный промпт** — роль и регламент для LLM (в начало user-сообщения)
- **Критерии** — ключ (`greeting`), название, вес %, макс. балл, промпт критерия

Ответ LLM — строго JSON: `total_score`, `summary`, `client_pains`, `call_outcome`, `criteria_results`.

Подробнее: [pipeline.md](pipeline.md).
