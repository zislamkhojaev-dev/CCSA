# Устранение неполадок

## ASR не работает / `model_name = mock`

**Симптомы:** пустой транскрипт, в БД `model_name` с mock, в `/health` STT `model_loaded: false`.

**Действия:**

```bash
docker compose logs stt-service --tail 80
curl -s http://localhost:8001/health | python3 -m json.tool
```

- Проверьте наличие `models/OvozifyLabs--whisper-small-uz-v1-int8/model.bin`
- При ошибке загрузки — `make convert-stt-model` или см. [models/README.md](../models/README.md)
- Перезапуск: `docker compose restart stt-service`

На карточке звонка: **Повторное распознавание (ASR)**.

---

## Зависание «Распознавание ASR» (нет нагрузки CPU)

**Причина:** залипший семафор Redis или параллельная перегрузка STT.

**Действия:**

1. Плейграунд: снова **Запустить анализ** (сбрасывает слоты и `transcribing` → `queued`)
2. Перезапуск worker:
   ```bash
   docker compose restart celery-worker api
   ```
3. Очистка Redis вручную:
   ```bash
   docker compose exec redis redis-cli DEL ccsa:asr:holders ccsa:asr:active_count
   ```
4. В настройках: **макс. параллельных STT = 1**, **плейграунд по одному** включено

---

## `timed out` при транскрибации

- Увеличьте **Таймаут HTTP к STT** в настройках (600 → 1200)
- Уменьшите параллелизм до 1
- Проверьте длительность файла и ресурсы CPU
- Логи: `docker compose logs celery-worker stt-service --tail 100`

---

## LLM не отвечает / пустой анализ

- Проверьте API-ключ в **Настройки → Модели и AI**
- Для облака включена анонимизация PII — при выключенной без ключа будет ошибка
- Логи worker при `analyze_call`
- **Повторный анализ (LLM)** на карточке звонка

---

## Ошибка 500 при сохранении сценария

Исправлено в актуальной версии (async SQLAlchemy + `updated_at`).  
Обновите код и перезапустите `api`.

---

## Pyannote не работает

- Нужен `HF_TOKEN` в `.env`
- Принять лицензии моделей pyannote на Hugging Face
- Без токена — fallback на `stereo_channels` или `mono`

---

## Webitel не загружает звонки

- **Настройки → Коннекторы** — URL и токен, кнопка «Проверить»
- Логи: `docker compose logs celery-beat celery-worker | grep -i webitel`
- Расписание и окно времени в автоматизации

---

## Исследования (LLM метаанализ)

**Симптомы:** статус `error`, пустой отчёт, долгое выполнение.

**Действия:**

1. Текст ошибки на странице исследования (`error_message`)
2. Логи worker:
   ```bash
   docker compose logs celery-worker --tail 100 | grep -i research
   ```
3. Проверьте LLM-ключ в **Настройки → Модели и AI**
4. Убедитесь, что миграция применена: `make migrate`
5. Перезапуск после деплоя: `docker compose restart api celery-worker`

**«Нет звонков с транскриптом»** — расширьте период или дождитесь завершения ASR у звонков.

**«Слишком много звонков»** — сузьте фильтры или увеличьте `RESEARCH_MAX_CALLS` в `.env`.

Подробнее: [research.md](research.md).

---

## Полезные команды

```bash
# Статус контейнеров
docker compose ps

# Логи сервиса
docker compose logs -f api celery-worker stt-service

# Последние транскрипции
docker compose exec postgres psql -U ccsa -d ccsa -c \
  "SELECT id, call_id, status, model_name, left(full_text,40) FROM calls c JOIN transcriptions t ON t.call_id=c.id ORDER BY t.id DESC LIMIT 5;"

# Тесты API
docker compose exec api pytest -q
```
