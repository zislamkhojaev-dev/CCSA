# Разработка

## Локальная структура

| Каталог | Запуск |
|---------|--------|
| `backend/app` | `uvicorn app.main:app --reload` (нужны PG, Redis, MinIO) |
| `backend/worker` | `celery -A worker.celery_app worker -l info` |
| `backend/stt` | `uvicorn stt.main:app --port 8001` |
| `frontend` | `npm run dev` (прокси к API — через nginx или vite proxy) |

В Docker тома монтируют `./backend` и `./frontend` — изменения подхватываются без rebuild.

## Миграции БД

```bash
# Создать ревизию
docker compose exec api alembic revision --autogenerate -m "описание"

# Применить
make migrate
```

## Seed

```bash
make seed
# admin / admin123, демо-сценарий с критериями
```

## Тесты

```bash
make test
# или
docker compose exec api pytest -q backend/tests
```

## Линтер

```bash
make lint
```

## Добавление метрики дашборда

1. `backend/app/services/dashboard_metrics.py` — логика метрики
2. `frontend/src/types/dashboard.ts` — ключ, подпись, `suggestedWidgetDimensions`
3. Дефолтные виджеты в `backend/app/api/dashboard.py` (опционально)

Layout виджета: `{ id, type, title, metric, width: 1–4, height: 1–2 }`. Legacy `size`
(`small`/`medium`/`large`) мигрирует при загрузке.

## Добавление критерия в сценарий

Через UI или API: уникальный `key` (латиница), промпт критерия.  
LLM JSON Schema строится динамически по списку критериев сценария.

## Исследования (LLM метаанализ)

| Компонент | Путь |
|-----------|------|
| API | `backend/app/api/research.py` |
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
