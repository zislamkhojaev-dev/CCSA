# ASR Benchmark — сравнительное тестирование моделей

> **Спецификация:** [`EXPERIMENT.md`](EXPERIMENT.md) · **Каталог моделей:** [`MODELS.md`](MODELS.md)

Сравнение **5 локальных** ASR-моделей: WER/CER относительно baseline, время транскрибации и peak RSS на CPU.

**Волна 2 (план):** [Gearnode/qwen3-asr-uzbek-v2](https://huggingface.co/Gearnode/qwen3-asr-uzbek-v2), [facebook/mms-1b-all](https://huggingface.co/facebook/mms-1b-all) (uz `uzb-script_latin`) — см. [`MODELS.md`](MODELS.md).

## Модели (5 локальных)

| Slug | Модель | Движок |
|------|--------|--------|
| `ovozify-transformers-fp32` | OvozifyLabs/whisper-small-uz-v1 | transformers, fp32 (**baseline**) |
| `zehnova-transformers` | Jonibek21/Zehnova-Uzbek-STT | transformers |
| `ovozify-transformers-int8` | OvozifyLabs/whisper-small-uz-v1 | transformers, int8 (prepared) |
| `ovozify-ct2-fp32` | OvozifyLabs/whisper-small-uz-v1 | faster-whisper / CT2, float32 |
| `ovozify-ct2-int8` | OvozifyLabs/whisper-small-uz-v1 | faster-whisper / CT2, int8 |

Параметры: **language=uz**, **temperature=0**, **CPU**, моно, без диаризации.

**Эталон WER/CER:** `ovozify-transformers-fp32` (локальный baseline, не OpenAI).

## Гипотезы

| ID | Гипотеза | Критерий |
|----|----------|----------|
| H1 | int8 transformers не сильно хуже fp32 | Δ WER ≤ 5 п.п. vs baseline |
| H2 | CT2 fp32 не хуже transformers fp32 | Δ WER ≤ 0 |
| H3 | CT2 int8 не хуже transformers fp32 | Δ WER ≤ 0 |

---

## Быстрый старт

### 1. Окружение (из корня `CCSA/`)

```bash
python3 -m venv backend/.venv-benchmark
source backend/.venv-benchmark/bin/activate
make benchmark-deps
```

### 2. Hugging Face (быстрое скачивание ~3 GB Zehnova)

Скопируйте `benchmark/hf.env.example` → `benchmark/hf.env` или добавьте в корневой `.env`:

```bash
HF_HUB_ENABLE_HF_TRANSFER=1
HF_XET_HIGH_PERFORMANCE=1
HF_HUB_DOWNLOAD_TIMEOUT=600
HF_TOKEN=hf_...   # в `.env` одной строкой; не вставляйте токен в терминал как команду
```

Установите ускоритель и предзагрузите модели:

```bash
make benchmark-deps
make benchmark-download-hf      # Ovozify + Zehnova
# или только Zehnova (~3 GB):
make benchmark-download-zehnova

# волна 2 (пока только скачивание, см. MODELS.md)
make benchmark-download-wave2
```

Кэш по умолчанию: `models/hf-cache/`.

### 3. Подготовка локальных артефактов (CT2, int8)

```bash
make benchmark-setup
make benchmark-check
```

### 4. Аудио

`benchmark/audio/1.wav` … `6.wav` (моно).

### 5. Прогон

```bash
make benchmark-run
```

**6 файлов × 5 моделей = 30 транскрибаций.**

Только baseline + Zehnova (12 транскрибаций):

```bash
make benchmark-run-zehnova
```

### 6. Результаты

`benchmark/results/YYYYMMDD_HHMMSS/`:

- `results.json`, `results.csv`
- `transcripts/{model}/{n}.txt`

Колонки: `wer_vs_baseline`, `cer_vs_baseline`, `duration_sec`, `peak_rss_mb`.

### Пересчёт WER без повторной транскрибации

Если в `results.csv` пустые WER (старый прогон без эталона OpenAI / до обновления скрипта), но есть `transcripts/`:

```bash
cd backend
../backend/.venv-benchmark/bin/python scripts/asr_benchmark/attach_baseline_metrics.py \
  ../benchmark/results/20260521_100914
```

Или из корня: `make benchmark-metrics RUN_ID=20260521_100914`

---

## Опции

```bash
# только часть моделей
python scripts/asr_benchmark/run_benchmark.py --models ovozify-ct2-int8 zehnova-transformers
```

---

## Troubleshooting

| Проблема | Решение |
|----------|---------|
| `Missing model artifacts` | `make benchmark-setup` |
| `No audio files found` | `benchmark/audio/1.wav` … `6.wav` |
| Медленно на CPU | Нормально; модели идут по очереди |
| HF Read timeout | `make benchmark-download-zehnova`, проверьте `HF_HUB_ENABLE_HF_TRANSFER=1` и `pip install hf-transfer` |
| Zehnova ~3 GB | `make benchmark-download-zehnova` до прогона |
