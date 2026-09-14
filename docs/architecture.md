# Архитектура

## Общая схема

```mermaid
flowchart LR
  subgraph ui [Пользователь]
    Browser[Браузер :8080]
  end
  subgraph edge [nginx]
    Nginx[Прокси]
  end
  subgraph app [Приложение]
    FE[frontend React]
    API[api FastAPI]
    Worker[celery-worker llm/io]
    SttW[celery-worker-stt]
    Beat[celery-beat]
  end
  subgraph data [Данные]
    PG[(PostgreSQL)]
    Redis[(Redis)]
    MinIO[(MinIO)]
  end
  subgraph ai [AI]
    STT[stt-service]
    LLM[OpenAI / Gemini / Ollama]
  end
  Browser --> Nginx
  Nginx --> FE
  Nginx --> API
  API --> PG
  API --> Redis
  API --> MinIO
  Worker --> PG
  Worker --> Redis
  Worker --> MinIO
  Worker --> LLM
  SttW --> PG
  SttW --> Redis
  SttW --> STT
  Beat --> Worker
  Beat --> SttW
  STT --> MinIO
```

## Репозиторий

```
CCSA/
├── backend/           # API + Celery + STT (Python)
│   ├── app/           # FastAPI, модели, сервисы
│   ├── worker/        # Celery tasks, ASR limiter
│   ├── stt/           # Сервис распознавания (отдельный процесс)
│   └── alembic/       # Миграции БД
├── frontend/          # React SPA
├── nginx/             # Конфиг прокси
├── models/            # CT2-модели (не в git)
├── docs/              # Документация
└── docker-compose.yml
```

## Backend (`app/`)

| Модуль | Назначение |
|--------|------------|
| `api/*` | Тонкие контроллеры FastAPI (JWT, RBAC, делегирование в сервисы) |
| `services/*_service.py` | Домен: auth, calls, dashboard, operators, scenarios, tags, playground, research, settings |
| `ports.py` | Protocol-порты (Webitel, Storage, STT, Redis, TaskDispatcher) |
| `core/` | Логи, `trace_id`, `AppError` / `ErrorCode`, retry, feature flags, idempotency |
| `services/llm.py` | Промпт, JSON Schema, провайдеры LLM, cohort-анализ (`run_cohort_analysis`) |
| `services/research_query.py` | Выборка звонков с транскриптом для исследований |
| `services/pii.py` | Анонимизация перед облачным LLM |
| `services/storage.py` | Адаптер MinIO (`StoragePort`) |

## Слои backend

```mermaid
sequenceDiagram
  participant UI as Frontend
  participant API as API_controllers
  participant Svc as Domain_services
  participant Port as Ports_ACL
  participant Ext as Webitel_LLM_STT_MinIO
  participant DB as PostgreSQL
  UI->>API: HTTP
  API->>API: JWT_RBAC
  API->>Svc: command_or_query
  Svc->>Port: interface_call
  Port->>Ext: adapter_http
  Svc->>DB: ORM
```

Контроллеры в `app/api/` не содержат SQL и SDK. Бизнес-логика — `app/services/*_service.py`. Внешние системы — порты в `app/ports.py` и адаптеры (`webitel.py`, `storage.py`, `stt_client.py`, `llm.py`).

## Auth

```mermaid
sequenceDiagram
  participant Browser
  participant API
  participant AuthService
  participant DB
  Browser->>API: POST /auth/login
  API->>AuthService: login
  AuthService->>DB: find user
  AuthService->>AuthService: verify_password
  AuthService-->>Browser: Set-Cookie httponly JWT
```

## Webitel sync

```mermaid
sequenceDiagram
  participant Beat as celery_beat
  participant Task as sync_webitel_calls
  participant Flags as feature_flags
  participant Webitel as WebitelPort
  participant DB as PostgreSQL
  participant STT as transcribe_call
  Beat->>Task: schedule
  Task->>Flags: webitel_sync enabled
  Task->>Webitel: fetch_call_history
  Webitel-->>Task: items
  Task->>DB: upsert Call
  Task->>STT: delay transcribe
```

## Call export SSE

```mermaid
sequenceDiagram
  participant UI
  participant API
  participant CallService
  participant Celery
  participant Redis
  UI->>API: POST /calls/export/jobs
  API->>CallService: create job
  CallService->>Celery: run_calls_export
  UI->>API: GET /export/jobs/id/events
  Celery->>Redis: publish progress
  Redis-->>UI: SSE status
```

## Playground run

```mermaid
sequenceDiagram
  participant UI
  participant API
  participant PlaygroundService
  participant Storage as StoragePort
  participant Celery
  UI->>API: POST /playground/jobs
  UI->>API: POST upload
  API->>PlaygroundService: upload_files
  PlaygroundService->>Storage: upload_bytes
  UI->>API: POST run
  PlaygroundService->>Celery: process_playground_file
```

## Dashboard widgets

```mermaid
sequenceDiagram
  participant UI
  participant API
  participant DashboardService
  participant Metrics as dashboard_metrics
  participant DB
  UI->>API: GET /dashboard/layout
  API->>DashboardService: load_user_widgets
  UI->>API: POST /metrics/batch
  API->>Metrics: fetch_widget_metric
  Metrics->>DB: aggregations
```

## Worker (`worker/`)

| Задача | Описание |
|--------|----------|
| `webitel.sync_webitel_calls` | Загрузка записей из Webitel (по расписанию) |
| `pipeline.transcribe_call` | ASR одного звонка |
| `pipeline.analyze_call` | LLM-анализ |
| `pipeline.process_pending_batch` | Очередь pending/transcribed (каждые 5 мин) |
| `pipeline.recover_stuck_calls` | Возврат брошенных обработок в очередь (каждые 10 мин) |
| `pipeline.backfill_topics` | Классификация тем у звонков без темы (по кнопке) |
| `playground.process_playground_file` | ASR + LLM для файла плейграунда |
| `research.run_research_study` | LLM метаанализ по выборке звонков |

Очереди Celery: `stt` (ASR, concurrency=1), `llm` (анализ), `io` (sync/export/batch). Воркеры: `celery-worker` (`llm,io`) и `celery-worker-stt` (`stt`).

Ограничение параллельных запросов к STT: `worker/asr_limit.py` (Redis, токены с TTL).

Блокировки задач на звонок: `worker/task_lock.py` (Redis, ключи с TTL). Статус звонка —
состояние для пользователя, не примитив синхронизации: упавший worker освобождает лок по TTL,
а `recover_stuck_calls` возвращает звонок в очередь. Подробнее: [pipeline.md](pipeline.md#блокировки-и-восстановление).

## STT (`stt/`)

Отдельный FastAPI-процесс внутри docker-сети (порт 8001 не публикуется на хост).

- Движки: **faster-whisper (CT2)** или **transformers** pipeline
- Диаризация: `stereo_channels` (левый/правый канал), `pyannote`, `mono`
- Endpoint: `POST /transcribe` — `storage_key` в MinIO, заголовок `X-STT-Token`

## Frontend

- React Router, TanStack Query
- Страницы: дашборд (конструктор виджетов), звонки, операторы, сценарии, **исследования** (`/research`), плейграунд, настройки
- Аудио: WaveSurfer, транскрипт с seek

## Исследования

См. [research.md](research.md). Кратко: UI → API → Celery `run_research_study` → выборка транскрибированных звонков → LLM Markdown-отчёт в `research_studies`.

## Безопасность

- Пароли: bcrypt
- Секреты настроек: Fernet (`SETTINGS_ENCRYPTION_KEY`)
- Сессии через cookie (см. `api/auth`)
- Роли: admin / supervisor. Destructive операции (bulk-delete, delete scenario/research, operator sync, retranscribe/reanalyze) — admin
- Ошибки: [error-codes.md](error-codes.md)
- Production: обязательны `SECRET_KEY`, `SETTINGS_ENCRYPTION_KEY`, `SEED_ADMIN_PASSWORD`, `CORS_ORIGINS` (без dev-дефолтов)
