# Журнал изменений

## 2026-10-27 — Идемпотентность, загрузки, PII, readiness и версии стека

- `Idempotency-Key` занимается вставкой до побочного эффекта. Повтор с тем же телом возвращает сохранённый ответ, другое тело — `IDEMPOTENCY_CONFLICT`, ещё не завершённый ключ — `IDEMPOTENCY_IN_PROGRESS`. Нужна миграция `009_idempotency_state`.
- Плейграунд больше не читает файлы без лимита: количество, размер, расширение и MIME задаются через `UPLOAD_MAX_FILES` и `UPLOAD_MAX_BYTES`.
- PII перед облачным LLM: телефоны без `+998`, произнесённые номера, имена после «меня зовут» / `ismim`, адреса. Оригиналы можно восстановить через зашифрованный vault; в модель и в логи уходит только `[PII_DATA]`.
- Миграции выполняет сервис `migrate`. `GET /ready` проверяет Postgres, Redis и MinIO и отвечает 503, если зависимость недоступна.
- Backend: FastAPI 0.162, SQLAlchemy 2.1.6, Pydantic 2.14, Alembic 1.20, Celery 5.6, OpenAI SDK 3.40. Frontend: React 19.3, TypeScript 7, TanStack Query 5.105, lucide-react 1.62, wavesurfer.js 8.
- SQLAlchemy 2.1 трактует голый `postgresql://` как psycopg 3. Синхронный URL приводится к `postgresql+psycopg2`, старые значения в `.env` продолжают работать.

## 2026-10-27 — Обновление критичных зависимостей и AI safety

- `python-jose` заменён на PyJWT 2.15; JWT содержит `iss`, `aud`, `iat`, `nbf`, `jti`, а `sub` хранит immutable user id.
- OpenAI переведён с Chat Completions на Responses API со строгим JSON Schema и `store=false`.
- LLM больше не создаёт успешную mock-оценку при отсутствии ключа или невалидном ответе.
- Итоговый балл вычисляется приложением из проверенных баллов критериев.
- Неизвестный LLM-провайдер отклоняется до отправки транскрипта; Gemini API key передаётся заголовком.
- Удалён ложный alias FastConformer, фактически запускавший другую Whisper-модель.
- Mono-диаризация обновлена до pyannote Community-1; стерео-каналы остаются основным режимом.
- Frontend: Node 24, React Router 7, Vite 8, Vitest 5; `npm audit` не показывает уязвимостей.
- CI теперь выполняет frontend audit, TypeScript, тесты и production build.

После деплоя пользователям потребуется войти повторно: старые JWT использовали login
в `sub` и не содержали обязательные `iss` / `aud` / `jti`.

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
