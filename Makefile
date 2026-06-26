.PHONY: up down build logs migrate seed shell test lint

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python -m app.scripts.seed

shell:
	docker compose exec api bash

test:
	docker compose exec api pytest -q

lint:
	docker compose exec api ruff check app worker
	docker compose exec api ruff format --check app worker

gpu-up:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

convert-stt-model:
	cd backend && python3 scripts/convert_whisper_to_ct2.py \
		--model OvozifyLabs/whisper-small-uz-v1 \
		--output ../models/OvozifyLabs--whisper-small-uz-v1-int8

# Absolute path: targets run `cd backend`, so a relative venv path would break.
BENCHMARK_PYTHON := $(CURDIR)/backend/.venv-benchmark/bin/python
# Wave 2 (Qwen3-ASR) needs Python >= 3.10
BENCHMARK_PYTHON_WAVE2 := $(CURDIR)/backend/.venv-benchmark311/bin/python

benchmark-setup:
	cd backend && $(BENCHMARK_PYTHON) scripts/asr_benchmark/setup_models.py

benchmark-setup-smoke:
	cd backend && $(BENCHMARK_PYTHON) scripts/asr_benchmark/setup_models.py --smoke

benchmark-check:
	cd backend && $(BENCHMARK_PYTHON) scripts/asr_benchmark/run_benchmark.py --check-artifacts-only

benchmark-run:
	cd backend && $(BENCHMARK_PYTHON) scripts/asr_benchmark/run_benchmark.py

benchmark-download-hf:
	cd backend && $(BENCHMARK_PYTHON) scripts/asr_benchmark/download_hf_models.py

benchmark-download-zehnova:
	cd backend && $(BENCHMARK_PYTHON) scripts/asr_benchmark/download_hf_models.py --zehnova-only

# Wave 2 models (see benchmark/MODELS.md)
# Wave 2: MMS only by default (Qwen ~4 GB skipped; use --include-qwen when ready)
benchmark-download-wave2:
	cd backend && PYTHONUNBUFFERED=1 HF_HUB_ENABLE_HF_TRANSFER=0 $(BENCHMARK_PYTHON) scripts/asr_benchmark/download_hf_models.py --wave2-only --no-hf-transfer

benchmark-download-wave2-all:
	cd backend && PYTHONUNBUFFERED=1 HF_HUB_ENABLE_HF_TRANSFER=0 $(BENCHMARK_PYTHON_WAVE2) scripts/asr_benchmark/download_hf_models.py --wave2-only --include-qwen --no-hf-transfer

BENCHMARK_BASELINE_RUN ?= 20260521_100914

benchmark-deps-wave2:
	$(BENCHMARK_PYTHON_WAVE2) -m pip install -r benchmark/requirements.txt -r benchmark/requirements-wave2.txt torch torchaudio transformers accelerate huggingface-hub hf-transfer

benchmark-run-wave2:
	cd backend && $(BENCHMARK_PYTHON) scripts/asr_benchmark/run_benchmark.py --wave2-only --baseline-from ../benchmark/results/$(BENCHMARK_BASELINE_RUN)

benchmark-run-zehnova:
	cd backend && $(BENCHMARK_PYTHON) scripts/asr_benchmark/run_benchmark.py --models ovozify-transformers-fp32 zehnova-transformers

benchmark-metrics:
	cd backend && $(BENCHMARK_PYTHON) scripts/asr_benchmark/attach_baseline_metrics.py ../benchmark/results/$(RUN_ID)

benchmark-deps:
	$(BENCHMARK_PYTHON) -m pip install -r backend/requirements-stt.txt -r benchmark/requirements.txt

init: build up
	@echo "Waiting for services..."
	@sleep 15
	$(MAKE) migrate
	$(MAKE) seed
	docker compose restart nginx
	@echo "Ready at http://localhost:8080"
