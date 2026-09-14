# Разработка

## Локальная структура

| Каталог | Запуск |
|---------|--------|
| `backend/app` | `uvicorn app.main:app --reload` (нужны PG, Redis, MinIO) |
| `backend/worker` | `celery -A worker.celery_app worker -l info` |
| `backend/stt` | `uvicorn stt.main:app --port 8001` (нужен `STT_SERVICE_TOKEN`) |
| `frontend` | `npm run dev` (прокси к API — через nginx или vite proxy) |

В Docker тома монтируют `./backend` и `./frontend` — изменения подхватываются без rebuild.

Слои: контроллеры `app/api/` только парсят HTTP и вызывают сервисы. SQL и оркестрация — `app/services/*_service.py`. Внешние системы — порты в `app/ports.py` и адаптеры. Ошибки — `AppError` / `ErrorCode` (`app/core/errors.py`), не сырой `HTTPException(detail=str(e))`. Логи — `get_logger()` из `app/core/logging.py`. Журнал изменений: [changelog.md](changelog.md).

## Миграции БД

```bash
# Создать ревизию
docker compose exec api alembic revision --autogenerate -m "описание"

# Применить
make migrate
```

Актуальная ревизия production-readiness: `008_idempotency_keys`. После pull на окружение: `make migrate`.

## Seed

```bash
make seed
# логин/пароль из SEED_ADMIN_LOGIN / SEED_ADMIN_PASSWORD, демо-сценарий с критериями
```

## Тесты

`backend/pytest.ini` задаёт `pythonpath = .`. Из корня репозитория или каталога `backend`:

```bash
make test
# или локально (venv Python 3.11+):
cd backend && .venv/bin/pytest -q
```

Основные файлы: `backend/tests/conftest.py` (моки портов), `test_observability.py`, `test_recovery_and_services.py`, `test_worker_locks.py`, плюс существующие `test_research_query.py` и др.

Фронтенд (vitest):

```bash
cd frontend && npm test
```

CI (`.github/workflows/ci.yml`): ruff + pytest + vitest.

## Линтер

```bash
make lint
```

## Добавление метрики дашборда

1. `backend/app/services/dashboard_metrics.py` — логика метрики
2. `frontend/src/types/dashboard.ts` — ключ, подпись, `suggestedWidgetDimensions`
3. Дефолтные виджеты в `backend/app/services/dashboard_service.py` (`DEFAULT_WIDGETS`, опционально)

Layout виджета: `{ id, type, title, metric, width: 1–4, height: 1–2 }`. Legacy `size`
(`small`/`medium`/`large`) мигрирует при загрузке.

## Добавление критерия в сценарий

Через UI или API: уникальный `key` (латиница), промпт критерия.  
LLM JSON Schema строится динамически по списку критериев сценария.

## Исследования (LLM метаанализ)

| Компонент | Путь |
|-----------|------|
| API | `backend/app/api/research.py` → `research_service.py` |
| Схемы | `backend/app/schemas/research.py` |
| Выборка звонков | `backend/app/services/research_query.py` |
| LLM cohort | `backend/app/services/llm.py` → `run_cohort_analysis` |
| Celery | `backend/worker/tasks/research.py` |
| Модель БД | `ResearchStudy` в `backend/app/models/entities.py` |
| UI | `frontend/src/pages/ResearchListPage.tsx`, `ResearchNewPage.tsx`, `ResearchDetailPage.tsx` |

Миграция: `backend/alembic/versions/002_research_studies.py` → `make migrate`.

Тесты выборки: `backend/tests/test_research_query.py`.

Документация: [research.md](research.md).

## STT: смена модели

1. Конвертация CT2 (если нужно): `make convert-stt-model`
2. `.env`: `STT_MODEL=…`
3. `docker compose restart stt-service`

## Git

- `models/*` — в `.gitignore`
- Секреты только в `.env`, не коммитить

## Документация

Исходники документации: `docs/`. При изменении архитектуры обновляйте соответствующий файл и оглавление в `docs/README.md`.
