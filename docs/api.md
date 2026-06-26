# API

Базовый URL через nginx: `/api/v1`  
Прямой доступ к API (dev): `http://localhost:8000/api/v1`  
Интерактивная документация: `http://localhost:8000/docs`

Аутентификация: сессионная cookie после `POST /api/v1/auth/login`.

## Основные группы endpoints

### Auth

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/auth/login` | Вход |
| POST | `/auth/logout` | Выход |
| GET | `/auth/me` | Текущий пользователь |

### Calls

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/calls` | Список (пагинация, фильтры) |
| GET | `/calls/{id}` | Детали + транскрипт + анализ |
| PATCH | `/calls/{id}/tags` | Теги |
| POST | `/calls/{id}/notes` | Заметка |
| POST | `/calls/{id}/retranscribe` | Повтор ASR + LLM |
| POST | `/calls/{id}/reanalyze` | Повтор LLM |
| GET | `/calls/{id}/audio` | URL аудио |

### Dashboard

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/dashboard/summary` | Сводные цифры |
| GET | `/dashboard/metrics?metric=…&period_days=30` | Данные виджета |
| GET | `/dashboard/metrics/available` | Список метрик |
| GET/PUT | `/dashboard/layout` | Layout конструктора (per user) |

### Scenarios

| Метод | Путь | Описание |
|-------|------|----------|
| GET/POST | `/scenarios` | Список / создание |
| GET/PUT/DELETE | `/scenarios/{id}` | CRUD |
| POST | `/scenarios/{id}/copy` | Копия |
| GET | `/scenarios/{id}/export` | JSON export |

### Playground

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/playground/jobs` | Новая сессия |
| POST | `/playground/jobs/{id}/upload` | Загрузка файлов |
| POST | `/playground/jobs/{id}/run` | Запуск анализа |
| GET | `/playground/jobs/{id}` | Статус и файлы |
| GET | `/playground/jobs/{id}/events` | SSE обновления |
| POST | `/playground/files/{id}/promote-to-calls` | Один файл в общую базу |
| POST | `/playground/jobs/{id}/promote-to-calls` | Все готовые файлы сессии в общую базу |

### Research (LLM метаанализ)

Подробное описание: [research.md](research.md).

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/research` | Список исследований (пагинация) |
| POST | `/research/preview` | Предпросмотр: число звонков с транскриптом по фильтрам |
| POST | `/research` | Создать исследование и запустить Celery-задачу |
| GET | `/research/{id}` | Детали + Markdown-отчёт |
| GET | `/research/filter-options` | Списки очередей и тегов для фильтров |
| GET | `/research/{id}/events` | SSE-прогресс анализа |
| GET | `/research/{id}/export?format=md\|json` | Скачать отчёт (Markdown или JSON) |
| DELETE | `/research/{id}` | Удалить исследование |

**Фильтры** (`filters`):

| Поле | Тип | Описание |
|------|-----|----------|
| `date_from` | string | `YYYY-MM-DD`, начало периода |
| `date_to` | string | `YYYY-MM-DD`, конец периода (включительно) |
| `direction` | string | `inbound` или `outbound` (опционально) |
| `operator_id` | int | ID оператора (опционально) |

**Лимит:** `RESEARCH_MAX_CALLS` (по умолчанию 200). Если preview или create возвращает `400` — сузьте фильтры.

**Пример preview:**

```json
POST /research/preview
{
  "filters": {
    "date_from": "2026-03-01",
    "date_to": "2026-03-31",
    "direction": "inbound"
  }
}
```

Ответ: `{ "count": 42, "max_calls": 200 }`

**Пример создания:**

```json
POST /research
{
  "title": "Жалобы клиентов — март",
  "prompt": "Какие основные причины недовольства? Выдели темы и цитаты.",
  "filters": {
    "date_from": "2026-03-01",
    "date_to": "2026-03-31"
  }
}
```

Ответ `201`: объект исследования (`id`, `status: "pending"`, `call_count: null`, …). Отчёт появится после завершения Celery-задачи (`GET /research/{id}` → `report_markdown`).

**Статусы:** `pending` → `running` → `completed` | `error`

### Settings (admin для PUT)

| Метод | Путь | Описание |
|-------|------|----------|
| GET/PUT | `/settings/models` | ASR/LLM/производительность |
| GET/PUT | `/settings/webitel` | Webitel |
| GET/PUT | `/settings/automation` | Автоматизация |
| GET/POST/PATCH | `/settings/users` | Пользователи |

### Operators

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/operators` | Список |
| POST | `/operators/sync` | Синхронизация |

### Health

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Статус API |

## Коды ответов

- `401` — не авторизован
- `403` — нет прав (например, настройки для non-admin)
- `422` — ошибка валидации тела запроса
- `500` — внутренняя ошибка (см. логи `api` / `celery-worker`)
