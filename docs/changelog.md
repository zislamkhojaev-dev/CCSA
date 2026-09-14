# Журнал изменений

## 2026-09-14 — Production readiness (соответствие `.cursorrules`)

Крупный рефакторинг API, безопасности, наблюдаемости и восстановления после сбоев. Поведение UI для оператора почти не меняется; меняются контракт ошибок, пагинация части списков и доступ к STT.

### Для эксплуатации (после обновления)

1. Применить миграцию: `make migrate` (ревизия `008_idempotency_keys`).
2. В `.env` задать `STT_SERVICE_TOKEN` (в compose по умолчанию `ccsa-stt-internal`). Порт `8001` на хост больше не пробрасывается.
3. Для `APP_ENV=production` обязательны: `SECRET_KEY`, `SETTINGS_ENCRYPTION_KEY`, `SEED_ADMIN_PASSWORD`, `CORS_ORIGINS`. Иначе API не стартует.
4. Форма входа больше не подставляет `admin` / `admin123`. Пароль сида по-прежнему берётся из `SEED_ADMIN_PASSWORD` (в `.env.example` для dev — `admin123`).

### Архитектура

Контроллеры FastAPI тонкие: SQL, оркестрация Celery и вызовы внешних систем живут в сервисах.

| Сервис | Файл |
|--------|------|
| Auth, cookie JWT | `backend/app/services/auth_service.py` |
| Звонки, экспорт, теги, заметки | `backend/app/services/call_service.py` |
| Дашборд summary / layout | `backend/app/services/dashboard_service.py` |
| Операторы и sync Webitel | `backend/app/services/operator_service.py` |
| Сценарии | `backend/app/services/scenario_service.py` |
| Теги | `backend/app/services/tag_service.py` |
| Плейграунд | `backend/app/services/playground_service.py` |
| Исследования | `backend/app/services/research_service.py` |
| Пользователи, automation, тест коннекторов | `backend/app/services/settings_admin_service.py` |

Порты (Anti-Corruption Layer) — `backend/app/ports.py`. Адаптеры: `WebitelClient`, `StorageService`, `SttClient`, `RedisEventBus`, `TaskDispatcher`. Единый Redis-клиент: `backend/app/services/redis_client.py`.

Диаграммы потоков: [architecture.md](architecture.md).

### Безопасность

- XSS: подсветка триггеров в транскрипте — React-узлы (`frontend/src/utils/highlightTranscript.ts`), без `dangerouslySetInnerHTML`.
- Cookie `HttpOnly` + `Secure` вне `development`.
- CORS: в development `*`, в production — список `CORS_ORIGINS`.
- RBAC: destructive операции только для роли `admin` — bulk-delete звонков, удаление сценария/исследования, sync операторов, retranscribe / reanalyze. Тест Webitel — admin. SSE плейграунда и исследований проверяют владельца (или admin).
- STT `/transcribe` требует заголовок `X-STT-Token`; сервис недоступен с хоста.

### Наблюдаемость и ошибки

- JSON-логи с `trace_id`, `user_id`, именем метода; секреты редактируются.
- Заголовок ответа `X-Request-ID`; тот же id уходит в Celery headers.
- Единый контракт ошибок `{ error_code, message, trace_id }` — [error-codes.md](error-codes.md).
- `Call.error_message` / ошибки playground / research / export — пользовательский текст, не `str(e)`.

### Recovery

- Таймауты LLM, Webitel, Postgres (`statement_timeout`, `pool_timeout`, connect timeout) — в [configuration.md](configuration.md).
- Retry Webitel и LLM с экспоненциальной задержкой и jitter.
- Заголовок `Idempotency-Key` на `POST /research`, `/playground/jobs`, `/calls/export/jobs`, `/calls/{id}/notes`, `/calls/bulk-delete`. Таблица `idempotency_keys`.

### Данные и API

Списки с `Paginated`: `{ items, total, page, page_size }`

| Было | Стало |
|------|--------|
| `GET /scenarios` → массив | `Paginated[ScenarioOut]` (`page_size` до 200) |
| `GET /tags?limit=` → массив | `Paginated[TagOut]` (`page`, `page_size`) |
| `GET /settings/users` → массив | `Paginated[UserOut]` |

`GET /research/filter-options` ограничен `FILTER_OPTIONS_LIMIT` (по умолчанию 500).

### Feature toggles

Env (перекрывают `app_settings`): `FEATURE_RESEARCH`, `FEATURE_PLAYGROUND`, `FEATURE_WEBITEL_SYNC`, `FEATURE_DASHBOARD_CONSTRUCTOR`. Выключенный флаг даёт `FEATURE_DISABLED` (403). Beat пропускает Webitel sync, если флаг выключен.

### Тесты

- Backend: `pytest` (pythonpath задан в `backend/pytest.ini`). Моки портов, fail-fast production config, operator sync, STT/lock, XSS-регресс подсветки.
- Frontend: `cd frontend && npm test` (vitest: `highlightTranscript`, `dashboardFilters`).
- CI: ruff + pytest + frontend vitest.

### Миграции

| Ревизия | Суть |
|---------|------|
| `008_idempotency_keys` | Таблица идемпотентности (`user_id` + `key`, FK на `users`) |
