# Каталог ASR-моделей для бенчмарка CCSA

Сводная таблица: что уже в прогоне, что планируется.  
Спецификация эксперимента: [`EXPERIMENT.md`](EXPERIMENT.md). Запуск: [`README.md`](README.md).

**Baseline для WER/CER:** `ovozify-transformers-fp32` (`OvozifyLabs/whisper-small-uz-v1`).

---

## Статус в бенчмарке

| Slug | HF ID | Статус | Движок в коде |
|------|-------|--------|---------------|
| `ovozify-transformers-fp32` | [OvozifyLabs/whisper-small-uz-v1](https://huggingface.co/OvozifyLabs/whisper-small-uz-v1) | ✅ в прогоне | `transformers` (Whisper) |
| `zehnova-transformers` | [Jonibek21/Zehnova-Uzbek-STT](https://huggingface.co/Jonibek21/Zehnova-Uzbek-STT) | ✅ в прогоне | `transformers` (Whisper Medium) |
| `ovozify-transformers-int8` | локальный артефакт | ✅ в прогоне | `transformers` (dynamic int8) |
| `ovozify-ct2-fp32` | локальный CT2 | ✅ в прогоне | `faster-whisper` |
| `ovozify-ct2-int8` | локальный CT2 | ✅ в прогоне | `faster-whisper` |
| `qwen3-asr-uzbek-v2` | [Gearnode/qwen3-asr-uzbek-v2](https://huggingface.co/Gearnode/qwen3-asr-uzbek-v2) | ⏸ отложено (~4 GB) | `qwen_asr` (Py3.11, `--include-qwen`) |
| `mms-1b-all-uz` | [facebook/mms-1b-all](https://huggingface.co/facebook/mms-1b-all) | ✅ волна 2 | MMS / Wav2Vec2 CTC |

---

## Планируемые модели (волна 2)

### 1. Qwen3-ASR Uzbek v2

| Поле | Значение |
|------|----------|
| **Репозиторий** | https://huggingface.co/Gearnode/qwen3-asr-uzbek-v2 |
| **Предлагаемый slug** | `qwen3-asr-uzbek-v2` |
| **База** | [Qwen/Qwen3-ASR-1.7B](https://huggingface.co/Qwen/Qwen3-ASR-1.7B) |
| **Размер** | ~2B параметров (BF16 в карточке) |
| **Лицензия** | Apache-2.0 |
| **Язык** | Uzbek (`uz`), в API — `language=["Uzbek"]` |
| **Обучение** | FLEURS + Uzbek Speech Corpus + YouTube (IT/News/Podcasts), fine-tune от v1 |

**Заметки для интеграции в бенчмарк:**

- Официальный инференс через пакет **`qwen_asr`**, не стандартный `transformers` pipeline Whisper.
- В карточке пример на **CUDA + bfloat16 + flash_attention_2**; для CPU-бенчмарка нужен отдельный путь (fp32/float32, без FA2) и оценка RSS/времени.
- Опционально: `forced_aligner` ([Qwen/Qwen3-ForcedAligner-0.6B](https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B)) — для бенчмарка без таймкодов можно отключить.
- Автор отмечает: на узбекском лучше MMS и Whisper large-v3; **повторы** — post-processing в их пайплайне (учесть при сравнении с Ovozify/Zehnova).
- Зависимости (ожидаемо): `qwen-asr`, `torch`, `transformers`, возможно отдельный venv.

**Черновик вызова (из model card):**

```python
from qwen_asr import Qwen3ASRModel

model = Qwen3ASRModel.from_pretrained(
    "Gearnode/qwen3-asr-uzbek-v2",
    device_map="cpu",  # для нашего бенчмарка
    dtype=torch.float32,
    max_new_tokens=448,
)
results = model.transcribe(
    audio=[(audio_array, 16000)],
    language=["Uzbek"],
    return_time_stamps=False,
)
text = results[0].text
```

**Предзагрузка HF:**

```bash
make benchmark-download-hf   # после добавления ID в download_hf_models.py
# или вручную: huggingface-cli download Gearnode/qwen3-asr-uzbek-v2
```

---

### 2. Meta MMS-1B (все языки, адаптер Uzbek Latin)

| Поле | Значение |
|------|----------|
| **Репозиторий** | https://huggingface.co/facebook/mms-1b-all |
| **Предлагаемый slug** | `mms-1b-all-uz` |
| **База** | Massively Multilingual Speech (MMS), ~1B |
| **Лицензия** | CC-BY-NC-4.0 (проверить допустимость для prod КЦ) |
| **Язык узбекский** | ISO в MMS: **`uzb-script_latin`** (латиница) |
| **Публикация** | [Scaling Speech Technology to 1,000+ Languages](https://arxiv.org/abs/2305.13516) |

**Заметки для интеграции:**

- Не Whisper: **Wav2Vec2 + CTC**, отдельный код в `transcribers` / движок `mms`.
- После загрузки процессора: `processor.tokenizer.set_target_lang("uzb-script_latin")` и `load_adapter("uzb-script_latin")`.
- В сравнении на странице Qwen3-Uzbek v2 автор оценивает MMS как **«passable»** для uz (хуже fine-tuned Qwen, но лучше generic Whisper на uz).
- Сэмплинг аудио: обычно **16 kHz** mono.
- Лицензия **NC** — зафиксировать в decision memo перед prod.

**Черновик вызова (типичный MMS):**

```python
import torch
from transformers import AutoProcessor, Wav2Vec2ForCTC

model_id = "facebook/mms-1b-all"
processor = AutoProcessor.from_pretrained(model_id)
model = Wav2Vec2ForCTC.from_pretrained(model_id)

processor.tokenizer.set_target_lang("uzb-script_latin")
processor.tokenizer.load_adapter("uzb-script_latin")

# audio_array: float32, 16 kHz
inputs = processor(audio_array, sampling_rate=16000, return_tensors="pt")
with torch.no_grad():
    logits = model(inputs.input_values).logits
ids = torch.argmax(logits, dim=-1)
text = processor.batch_decode(ids)[0]
```

**Предзагрузка HF:**

```bash
# huggingface-cli download facebook/mms-1b-all
```

---

## Размер эксперимента (после добавления волны 2)

| Этап | Моделей | Транскрибаций (6 файлов) |
|------|---------|---------------------------|
| Сейчас (волна 1) | 5 (+ baseline) | 30 |
| + Qwen3 + MMS | +2 | +12 → **42** |

Гипотезы H1–H3 относятся только к абляциям **Ovozify**; новые модели сравниваются по **WER vs baseline**, времени и RSS, плюс ручной просмотр (как Zehnova / CT2).

---

## Задачи на реализацию (чеклист)

- [ ] Добавить `Gearnode/qwen3-asr-uzbek-v2` и `facebook/mms-1b-all` в `hf_hub.BENCHMARK_HF_MODEL_IDS` и `download_hf_models.py`
- [ ] Зависимости: `benchmark/requirements-qwen.txt` / `requirements-mms.txt` или секция в README
- [ ] `config.py`: `ModelSpec` + engine `qwen_asr` | `mms`
- [ ] `transcribers.py`: отдельные loaders (CPU, без GPU-only опций по умолчанию)
- [ ] `make benchmark-run` с 7 моделями или `benchmark-run-wave2` target
- [ ] Обновить `EXPERIMENT.md` §3.1 и размер эксперимента после первого прогона wave 2
- [ ] Проверить лицензию MMS (CC-BY-NC) для коммерческого КЦ

---

## Ссылки

- Qwen3-ASR Uzbek v2: https://huggingface.co/Gearnode/qwen3-asr-uzbek-v2  
- Meta MMS-1B-all: https://huggingface.co/facebook/mms-1b-all  
- MMS languages / adapters: https://huggingface.co/facebook/mms-1b-all#supported-languages  
