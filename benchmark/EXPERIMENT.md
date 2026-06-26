# Дизайн эксперimenta: сравнительное тестирование ASR для КЦ

**Статус:** черновик спецификации  
**Цель:** выбрать оптимальную ASR-модель для контроля качества звонков КЦ (Uzbekistan)  
**Контекст проекта:** CCSA — локальный STT на faster-whisper / transformers, см. `backend/stt/`

---

## 1. Постановка задачи

### 1.1. Что измеряем

| Метрика | Описание |
|---------|----------|
| **WER** | Word Error Rate относительно эталона |
| **CER** | Character Error Rate относительно эталона |
| **duration_sec** | Wall-clock время транскрибации одного файла |
| **peak_rss_mb** | Peak RSS процесса (загрузка модели + inference на CPU) |

### 1.2. Что не измеряем

- Диаризация (спикеры) — **вне scope**
- Точность таймкодов — **вне scope**
- GPU / latency в prod-контейнере — бенчмарк только на **CPU**

### 1.3. Эталон качества (локальный baseline)

**Baseline:** `ovozify-transformers-fp32` (OvozifyLabs/whisper-small-uz-v1, transformers, fp32).

Все остальные модели сравниваются с транскриптами baseline по **WER/CER** (`wer_vs_baseline`, `cer_vs_baseline`).  
Для самого baseline метрики качества не считаются (эталон = сам себе).

> OpenAI (`whisper-1`, `gpt-4o-transcribe`) **исключены**: API не поддерживает `language=uz`, авто-детект давал неверные языки; локальный Ovozify fp32 даёт корректный узбекский текст.

---

## 2. Материал (датасет)

### 2.1. Состав

| ID файла | Описание | Кол-во |
|----------|----------|--------|
| `1` … `3` | «Хорошие» записи КЦ | 3 |
| `4` … `6` | «Плохие» записи КЦ | 3 |
| **Итого** | | **6** |

Критерий good/bad — качество звонка с точки зрения КЦ (задаёт заказчик); в автоматических метриках **не stratify**, но файлы можно пометить в manifest для ручного анализа.

### 2.2. Формат аудио

- Пользователь **сам** конвертирует стерео → **моно**
- Каталог: `benchmark/audio/`
- Имена: `1.wav`, `2.wav`, … `6.wav` (допустимы `.mp3`, `.ogg`, `.flac`, `.m4a`, `.webm`)
- Один канал, полная запись звонка целиком

### 2.3. Размер эксперimenta

```
6 файлов × 5 конфигураций = 30 транскрибаций
```

---

## 3. Модели и артеfакты

### 3.1. Матрица конфигураций (5 шт., только локальные)

| # | Slug | HF / путь | Движок | Квантизация | Нужна подготовка |
|---|------|-----------|--------|-------------|------------------|
| 1 | `ovozify-transformers-fp32` | `OvozifyLabs/whisper-small-uz-v1` | transformers | fp32 | скачивание HF (**baseline**) |
| 2 | `zehnova-transformers` | `Jonibek21/Zehnova-Uzbek-STT` | transformers | fp32 | скачивание HF |
| 3 | `ovozify-transformers-int8` | подготовленный артеfакт int8 | transformers | **int8** | **да — отдельный шаг** |
| 4 | `ovozify-ct2-fp32` | `models/OvozifyLabs--whisper-small-uz-v1-fp32/` | faster-whisper (CT2) | **float32** | **да — конвертация** |
| 5 | `ovozify-ct2-int8` | `models/OvozifyLabs--whisper-small-uz-v1-int8/` | faster-whisper (CT2) | int8 | уже в проекте |

> **Изменение относительно первого черновика:** CT2 **fp32** вместо float16; transformers int8 — **заранее подготовленный** артеfакт, а не только runtime dynamic quant.

### 3.2. Два движка

```
┌─────────────────────┐     ┌─────────────────────┐
│    transformers     │     │  faster-whisper     │
│  (Hugging Face)     │     │  (CTranslate2)      │
├─────────────────────┤     ├─────────────────────┤
│ ovozify fp32        │     │ ovozify CT2 fp32    │
│ ovozify int8        │     │ ovozify CT2 int8    │
│ zehnova             │     │                     │
└─────────────────────┘     └─────────────────────┘
```

Каждая конфигурация запускается **на своём движке** — без «перекладывания» int8 CT2 в transformers и наоборот.

### 3.4. Планируемые модели (волна 2)

Полное описание, slug, зависимости и черновики inference: **[`MODELS.md`](MODELS.md)**.

| Slug (план) | Hugging Face | Движок | Примечание |
|-------------|--------------|--------|------------|
| `qwen3-asr-uzbek-v2` | [Gearnode/qwen3-asr-uzbek-v2](https://huggingface.co/Gearnode/qwen3-asr-uzbek-v2) | `qwen_asr` (~2B, fine-tune Qwen3-ASR-1.7B) | Отдельный код; в карточке — CUDA/bf16, для бенчмарка нужен CPU-путь |
| `mms-1b-all-uz` | [facebook/mms-1b-all](https://huggingface.co/facebook/mms-1b-all) | MMS / Wav2Vec2 CTC | Язык: `uzb-script_latin`; лицензия **CC-BY-NC** — проверить для prod |

После подключения в коде: **6 × 7 = 42** транскрибации (при том же датасете).

### 3.3. Подготовка артеfактов Ovozify (детально)

#### A. Transformers fp32 (baseline)

- Источник: `OvozifyLabs/whisper-small-uz-v1` с Hugging Face Hub
- Загрузка: `AutoModelForSpeechSeq2Seq.from_pretrained(..., torch_dtype=float32)`
- Кэш: стандартный HF cache (`~/.cache/huggingface/`)

#### B. Transformers int8 — **требует реализации**

Цель: воспроизводимый артеfакт, одинаковый при каждом прогоне.

**Предлагаемый подход (CPU):**

1. Загрузить fp32 модель с Hub
2. Применить `torch.quantize_dynamic` на `torch.nn.Linear` → `torch.qint8`
3. Сохранить подготовленные веса + processor в каталог:
   ```
   models/OvozifyLabs--whisper-small-uz-v1-transformers-int8/
   ```
4. Бенчмарк загружает **только** из этого каталога (не квантует на лету)

Альтернатива (если dynamic quant нестабилен на Whisper): static quant через `optimum` / ONNX — зафиксировать в задаче 1.2 после пробного прогона.

#### C. CT2 fp32

```bash
python3 backend/scripts/convert_whisper_to_ct2.py \
  --model OvozifyLabs/whisper-small-uz-v1 \
  --output models/OvozifyLabs--whisper-small-uz-v1-fp32 \
  --quantization float32
```

Проверка готовности: наличие `model.bin` в каталоге.

#### D. CT2 int8

Уже описано в `models/README.md`:

```
models/OvozifyLabs--whisper-small-uz-v1-int8/model.bin
```

При отсутствии — `make benchmark-setup` или `convert_whisper_to_ct2.py --quantization int8`.

### 3.4. Единые параметры inference

| Параметр | Значение |
|----------|----------|
| `language` | `uz` |
| `temperature` | `0` |
| `device` | `cpu` |
| Диаризация | выключена |
| VAD (CT2) | `vad_filter=true` (как в prod STT) |
| beam_size (CT2) | `5` |
| chunk (transformers) | `chunk_length_s=30`, `stride_length_s=5` |

---

## 4. Гипотезы

Сравнение идёт по **среднему WER vs baseline** (`ovozify-transformers-fp32`) по 6 файлам.

| ID | Формулировка | Кандидат | Baseline | Критерий PASS |
|----|--------------|----------|----------|---------------|
| **H1** | INT8 на transformers не сильно хуже fp32 | `ovozify-transformers-int8` | `ovozify-transformers-fp32` | avg WER vs baseline ≤ **5%** |
| **H2** | CT2 fp32 не хуже transformers fp32 | `ovozify-ct2-fp32` | `ovozify-transformers-fp32` | avg WER vs baseline ≤ **0** (идентичный текст) |
| **H3** | CT2 int8 не хуже исходной transformers fp32 | `ovozify-ct2-int8` | `ovozify-transformers-fp32` | avg WER vs baseline ≤ **0** |

`wer_vs_baseline` = WER(транскрипт кандидата, транскрипт baseline на том же файле).

---

## 5. Процедура эксперimenta

### 5.1. Порядок прогона

```
1. Проверить наличие всех артеfактов (§3.3)
2. Локальные модели (по одной в RAM), baseline первым в списке:
   a. ovozify-transformers-fp32  (baseline)
   b. zehnova-transformers
   c. ovozify-transformers-int8
   d. ovozify-ct2-fp32
   e. ovozify-ct2-int8
3. Для каждой модели × файла:
   - транскрипт → transcripts/{slug}/{n}.txt
   - WER/CER vs baseline (кроме самого baseline)
   - duration_sec, peak_rss_mb
4. Агрегация + проверка H1–H3 → results.json
```

Модели грузятся **последовательно** (одна в RAM) для чистого RSS на CPU.

### 5.2. Нормализация текста для WER/CER

Перед сравнением:

1. Unicode NFKC
2. lower case
3. удаление пунктуации
4. схлопывание пробелов

Реализация: `backend/scripts/asr_benchmark/metrics.py` (jiwer).

### 5.3. Выходные артеfакты

```
benchmark/results/{run_id}/
├── results.json          # строки + summary + hypotheses
├── results.csv           # табличный вид
└── transcripts/
    ├── ovozify-transformers-fp32/
    ├── ovozify-transformers-int8/
    ├── ovozify-ct2-fp32/
    ├── ovozify-ct2-int8/
    └── zehnova-transformers/
```

---

## 6. Критерии успеха эксперimenta

Эксперiment считается **завершённым**, если:

- [ ] Все 30 транскрибаций выполнены без ошибок
- [ ] Для каждой модели (кроме baseline) заполнены WER/CER vs baseline
- [ ] Зафиксированы duration и peak RSS для каждой пары (модель × файл)
- [ ] Гипотезы H1–H3 посчитаны автоматически
- [ ] Принято решение: какая конфигурация идёт в prod STT (качество / скорость / память)

---

## 7. Риски и ограничения

| Риск | Митигация |
|------|-----------|
| Baseline не «истина», а согласованный эталон | Ручной просмотр `transcripts/` при спорных WER |
| Transformers int8 на CPU нестабилен | Зафиксировать метод в задаче 1.2; fallback на static/ONNX |
| CT2 fp32 — большой `model.bin`, медленно на CPU | Замерить; сравнить с int8 по RSS/времени |
| 6 файлов — малый sample | Использовать как pilot; при необходимости расширить датасет |

---

## 8. Разбивка на задачи

### Фаза 0 — Спецификация ✅

| ID | Задача | Исполнитель | Статус |
|----|--------|-------------|--------|
| 0.1 | Утвердить дизайн эксперimenta (этот документ) | команда | **в работе** |
| 0.2 | Зафиксировать CT2 fp32 вместо float16 | команда | согласовано |

---

### Фаза 1 — Подготовка моделей

| ID | Задача | Статус |
|----|--------|--------|
| 1.1 | CT2 fp32 | **done** (setup_models) |
| 1.2 | Transformers int8 artifact | **done** (`transformers_int8.py`) |
| 1.3 | CT2 int8 | **done** (setup_models) |
| 1.4 | Smoke-test (`--smoke`) | **done** |
| 1.5 | `setup_models.py` | **done** |
| 1.6 | `models/README.md` | **done** |
| 1.7 | Предзагрузка Zehnova (~3 GB) | `make benchmark-download-zehnova` | **done** / в работе |
| 1.8 | Qwen3-ASR + MMS: deps + адаптеры в бенчмарке | см. [`MODELS.md`](MODELS.md) | **todo** |

### Фаза 2 — Инструментарий бенчмарка

| ID | Задача | Статус |
|----|--------|--------|
| 2.1 | `config.py` (fp32 CT2, transformers int8 path) | **done** |
| 2.2 | `transcribers.py` (prepared int8 loader) | **done** |
| 2.3 | `run_benchmark.py` (H2, artifact checks) | **done** |
| 2.4 | `benchmark/README.md` | **done** |
| 2.5 | Makefile (`benchmark-setup`, `benchmark-check`) | **done** |
| 2.6 | Интеграция `qwen3-asr-uzbek-v2`, `mms-1b-all-uz` | `config`, `transcribers`, HF download | **todo** |

---

### Фаза 3 — Подготовка данных (заказчик)

| ID | Задача | Детали | Зависимости | Статус |
|----|--------|--------|-------------|--------|
| **3.1** | Конвертировать 6 записей стерео → **моно** | ffmpeg / Audacity / DAW | записи КЦ | todo |
| **3.2** | Разложить файлы `benchmark/audio/1…6` | 3 good + 3 bad | 3.1 | todo |
| **3.3** | (Опционально) `benchmark/audio/manifest.json` | `{ "1": "good", "4": "bad", ... }` для анализа | 3.2 | todo |

---

### Фаза 4 — Проведение эксперimenta

| ID | Задача | Детали | Зависимости | Статус |
|----|--------|--------|-------------|--------|
| **4.1** | Поднять venv + deps | `make benchmark-deps` | — | todo |
| **4.2** | `make benchmark-setup` | Все артеfакты Ovozify | Фаза 1 | todo |
| **4.3** | `make benchmark-run` | Полный прогон 30 транскрибаций | Фазы 2–3 | todo |
| **4.4** | Проверить completeness | 5×6 transcripts, WER для 4 кандидатов | 4.3 | todo |

---

### Фаза 5 — Анализ и решение

| ID | Задача | Детали | Зависимости | Статус |
|----|--------|--------|-------------|--------|
| **5.1** | Таблица: WER/CER × модель | `results.csv` / pivot | 4.4 | todo |
| **5.2** | Таблица: время + RSS × модель | выбор по ресурсам CPU | 4.4 | todo |
| **5.3** | Оценка H1, H2, H3 | `results.json → hypotheses` | 4.4 | todo |
| **5.4** | Ручной просмотр расхождений | 2–3 файла с max WER | 4.4 | todo |
| **5.5** | **Decision memo** | Рекомендация для prod STT + trade-offs | 5.1–5.4 | todo |

---

## 9. Диаграмма зависимостей задач

```
[0.1 Design doc]
       │
       ▼
┌──────────────────────────────────────┐
│  Фаза 1: артеfакты моделей           │
│  1.1 CT2 fp32  1.2 transformers int8│
│  1.3 CT2 int8  1.4 smoke  1.5 setup  │
└──────────────┬───────────────────────┘
               ▼
┌──────────────────────────────────────┐
│  Фаза 2: код бенчмарка (2.1–2.5)     │
└──────────────┬───────────────────────┘
               │
     ┌─────────┴─────────┐
     ▼                   ▼
[Фаза 3: аудио]    [4.1–4.3 env/setup]
     │                   │
     └─────────┬─────────┘
               ▼
        [4.4 benchmark-run]
               ▼
        [Фаза 5: анализ]
```

---

## 10. Связанные файлы (текущее состояние репозитория)

| Компонент | Путь | Соответствие дизайну |
|-----------|------|----------------------|
| Конвертация CT2 | `backend/stt/model_convert.py` | OK, нужен `--quantization float32` |
| CLI конвертации | `backend/scripts/convert_whisper_to_ct2.py` | OK |
| Бенчмарк | `backend/scripts/asr_benchmark/*` | **готово** (Фазы 1–2) |
| Операционный README | `benchmark/README.md` | актуально |
| Каталог моделей (в т.ч. wave 2) | `benchmark/MODELS.md` | **новый** |
| Этот документ | `benchmark/EXPERIMENT.md` | актуальная спецификация |

---

## 11. Следующий шаг

После утверждения документа — выполнить **Фазу 1** (подготовка артеfактов) и **Фазу 2** (обновление кода) перед загрузкой аудио и прогоном.
