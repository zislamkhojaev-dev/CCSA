# Локальные модели ASR (бенчмарк и STT-сервис)

Сконвертированные uz-модели хранятся здесь и монтируются в `stt-service`, чтобы **не конвертировать при каждой сборке Docker**.

## Артеfакты OvozifyLabs/whisper-small-uz-v1

| Путь | Движок | Квантизация | Назначение |
|------|--------|-------------|------------|
| `OvozifyLabs--whisper-small-uz-v1-int8/` | CT2 (faster-whisper) | int8 | prod STT |
| `OvozifyLabs--whisper-small-uz-v1-fp32/` | CT2 (faster-whisper) | float32 | ASR benchmark |
| `OvozifyLabs--whisper-small-uz-v1-transformers-int8/` | transformers | int8 (dynamic) | ASR benchmark |

**CT2:** в каталоге должен быть файл `model.bin`.  
**Transformers int8:** файлы `pytorch_model_int8.bin` и `quantization.json`.

## Подготовка всех артеfактов для бенчмарка

Из корня репозитория:

```bash
make benchmark-setup
# smoke-test после подготовки:
cd backend && python3 scripts/asr_benchmark/setup_models.py --smoke
```

Или по отдельности:

```bash
cd backend

# CT2 int8 (prod)
python3 scripts/convert_whisper_to_ct2.py \
  --model OvozifyLabs/whisper-small-uz-v1 \
  --output ../models/OvozifyLabs--whisper-small-uz-v1-int8

# CT2 fp32 (benchmark)
python3 scripts/convert_whisper_to_ct2.py \
  --model OvozifyLabs/whisper-small-uz-v1 \
  --output ../models/OvozifyLabs--whisper-small-uz-v1-fp32 \
  --quantization float32

# Transformers int8 (benchmark)
python3 scripts/asr_benchmark/setup_models.py --only transformers-int8
```

Нужны: `pip install torch ctranslate2 transformers huggingface-hub`

## Git

Каталог `models/*` в `.gitignore` (сотни MB). На новой машине — один раз `make benchmark-setup` или скопировать папки с диска.
