import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import httpx
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from app.config import get_settings
from app.models import Criterion, Scenario
from app.services.pii import CLOUD_PROVIDERS, prepare_text_for_llm

logger = logging.getLogger(__name__)

MAX_LLM_RETRIES = 3
COHORT_SINGLE_SHOT_MAX_CHARS = 80_000
COHORT_MAP_BATCH_SIZE = 15

COHORT_SYSTEM_PROMPT = """Ты аналитик колл-центра. На основе транскриптов звонков отвечай на исследовательский вопрос пользователя.
Структурируй ответ в Markdown: краткое резюме, ключевые выводы, повторяющиеся темы, типичные жалобы клиентов, цитаты (если уместно), рекомендации.
Пиши на языке транскриптов (узбекский или русский). Не выдумывай факты — опирайся только на предоставленные тексты."""


@dataclass(frozen=True)
class CohortCall:
    call_id: int
    call_timestamp: datetime | None
    direction: str | None
    duration: int | None
    operator_name: str | None
    full_text: str


class CriterionResult(BaseModel):
    score: int
    passed: bool
    comment: str
    status: str = "completed"


class AnalysisOutput(BaseModel):
    total_score: int = Field(ge=0, le=100)
    is_violation: bool = False
    summary: str = ""
    client_pains: str = ""
    call_outcome: str = ""
    criteria_results: dict[str, CriterionResult]


_CRITERION_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "score": {"type": "integer"},
        "passed": {"type": "boolean"},
        "comment": {"type": "string"},
        "status": {"type": "string", "enum": ["completed", "not_applicable"]},
    },
    "required": ["score", "passed", "comment", "status"],
    "additionalProperties": False,
}


def _analysis_json_schema(criteria: list[Criterion]) -> dict[str, Any]:
    """JSON Schema for OpenAI strict structured output (all objects need additionalProperties: false)."""
    criterion_props = {c.key: _CRITERION_RESULT_SCHEMA for c in criteria}
    return {
        "type": "object",
        "properties": {
            "total_score": {"type": "integer"},
            "is_violation": {"type": "boolean"},
            "summary": {"type": "string"},
            "client_pains": {"type": "string"},
            "call_outcome": {"type": "string"},
            "criteria_results": {
                "type": "object",
                "properties": criterion_props,
                "required": list(criterion_props.keys()),
                "additionalProperties": False,
            },
        },
        "required": [
            "total_score",
            "is_violation",
            "summary",
            "client_pains",
            "call_outcome",
            "criteria_results",
        ],
        "additionalProperties": False,
    }


def _build_prompt(scenario: Scenario, criteria: list[Criterion], transcript: str) -> str:
    criteria_block = "\n".join(
        f'- "{c.key}" ({c.name}, max {c.max_score}, weight {c.weight_percent}%): {c.prompt}'
        for c in criteria
    )
    return f"""{scenario.system_prompt}

Оцени транскрипт разговора колл-центра. Ответ — только JSON.

Критерии:
{criteria_block}

Транскрипт:
{transcript}
"""


def _call_openai(
    prompt: str,
    model: str,
    api_key: str,
    criteria: list[Criterion],
) -> dict[str, Any]:
    client = OpenAI(api_key=api_key)
    messages = [
        {
            "role": "system",
            "content": "Ты аналитик качества колл-центра. Отвечай строго в формате JSON по схеме.",
        },
        {"role": "user", "content": prompt},
    ]
    schema = _analysis_json_schema(criteria)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "call_analysis", "strict": True, "schema": schema},
            },
            temperature=0.2,
        )
    except Exception as schema_err:
        logger.warning("OpenAI json_schema failed, fallback to json_object: %s", schema_err)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.2,
        )
    raw = response.choices[0].message.content or "{}"
    return json.loads(raw)


def _call_ollama(prompt: str, model: str, base_url: str) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/api/chat"
    with httpx.Client(timeout=120.0) as client:
        r = client.post(
            url,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "Respond with JSON only."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",
            },
        )
        r.raise_for_status()
        content = r.json().get("message", {}).get("content", "{}")
        return json.loads(content)


async def analyze_transcript(
    scenario: Scenario,
    criteria: list[Criterion],
    transcript: str,
    *,
    anonymize: bool = True,
    provider: str = "openai",
    api_key: str | None = None,
    model: str | None = None,
    ollama_base_url: str | None = None,
    custom_system_prompt: str | None = None,
) -> AnalysisOutput:
    settings = get_settings()
    prov = (provider or "openai").lower()
    model_name = model or scenario.llm_model or settings.openai_model

    text = prepare_text_for_llm(
        transcript,
        provider=prov,
        anonymize_enabled=anonymize,
        require_anonymization_for_cloud=True,
    )

    scenario_copy = scenario
    if custom_system_prompt:
        scenario_copy = Scenario(
            id=scenario.id,
            name=scenario.name,
            system_prompt=custom_system_prompt,
            llm_model=scenario.llm_model,
        )

    prompt = _build_prompt(scenario_copy, criteria, text)
    last_error: Exception | None = None

    for attempt in range(MAX_LLM_RETRIES):
        try:
            if prov == "local" or prov == "ollama":
                base = ollama_base_url or await _get_setting_fallback("ollama_base_url", "http://host.docker.internal:11434")
                data = _call_ollama(prompt, model_name, base)
            elif prov == "gemini":
                data = await _call_gemini(prompt, model_name, api_key)
            else:
                key = api_key or settings.openai_api_key
                if not key:
                    return _mock_analysis(criteria)
                data = _call_openai(prompt, model_name, key, criteria)
            return AnalysisOutput.model_validate(data)
        except (json.JSONDecodeError, ValidationError, Exception) as e:
            last_error = e
            logger.warning("LLM attempt %s failed: %s", attempt + 1, e)
            prompt = prompt + f"\n\n(Предыдущий ответ невалиден: {e}. Верни корректный JSON.)"

    logger.error("LLM failed after retries: %s", last_error)
    return _mock_analysis(criteria, error=str(last_error))


async def _get_setting_fallback(key: str, default: str) -> str:
    return default


async def _call_gemini(prompt: str, model: str, api_key: str | None) -> dict[str, Any]:
    key = api_key or ""
    if not key:
        raise ValueError("Gemini API key not configured")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    with httpx.Client(timeout=120.0) as client:
        r = client.post(
            url,
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
        )
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)


def _mock_analysis(criteria: list[Criterion], error: str | None = None) -> AnalysisOutput:
    err_hint = (error or "")[:120]
    results = {}
    total = 0
    for c in criteria:
        score = c.max_score
        results[c.key] = CriterionResult(
            score=score,
            passed=True,
            comment="Оценка недоступна — повторите анализ" + (f" ({err_hint})" if err_hint else ""),
        )
        total += int(score * c.weight_percent / 100)
    return AnalysisOutput(
        total_score=min(total, 100),
        is_violation=False,
        summary="Анализ недоступен — проверьте ключ OpenAI и настройки LLM." + (f" {err_hint}" if err_hint else ""),
        client_pains="—",
        call_outcome="other",
        criteria_results=results,
    )


def _format_call_block(call: CohortCall, text: str) -> str:
    ts = call.call_timestamp.isoformat() if call.call_timestamp else "—"
    dur = f"{call.duration}s" if call.duration is not None else "—"
    op = call.operator_name or "—"
    direction = call.direction or "—"
    return (
        f"### Звонок #{call.call_id}\n"
        f"- Дата: {ts}\n"
        f"- Оператор: {op}\n"
        f"- Направление: {direction}\n"
        f"- Длительность: {dur}\n\n"
        f"{text}\n"
    )


def _build_cohort_dataset(calls: list[CohortCall], *, anonymize: bool, provider: str) -> str:
    blocks: list[str] = []
    for call in calls:
        text = prepare_text_for_llm(
            call.full_text,
            provider=provider,
            anonymize_enabled=anonymize,
            require_anonymization_for_cloud=True,
        )
        blocks.append(_format_call_block(call, text))
    return "\n---\n\n".join(blocks)


def _call_openai_text(
    system: str,
    user: str,
    model: str,
    api_key: str,
    *,
    timeout: float = 300.0,
) -> str:
    client = OpenAI(api_key=api_key, timeout=timeout)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
    )
    return (response.choices[0].message.content or "").strip()


def _call_ollama_text(system: str, user: str, model: str, base_url: str) -> str:
    url = base_url.rstrip("/") + "/api/chat"
    with httpx.Client(timeout=300.0) as client:
        r = client.post(
            url,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
            },
        )
        r.raise_for_status()
        return (r.json().get("message", {}).get("content") or "").strip()


def _call_gemini_text(system: str, user: str, model: str, api_key: str) -> str:
    key = api_key or ""
    if not key:
        raise ValueError("Gemini API key not configured")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    prompt = f"{system}\n\n{user}"
    with httpx.Client(timeout=300.0) as client:
        r = client.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def _invoke_cohort_llm(
    system: str,
    user: str,
    *,
    provider: str,
    model: str,
    api_key: str | None,
    ollama_base_url: str | None,
) -> str:
    settings = get_settings()
    prov = (provider or "openai").lower()
    if prov in ("local", "ollama"):
        base = ollama_base_url or "http://host.docker.internal:11434"
        return _call_ollama_text(system, user, model, base)
    if prov == "gemini":
        return _call_gemini_text(system, user, model, api_key)
    key = api_key or settings.openai_api_key
    if not key:
        raise ValueError("OpenAI API key not configured")
    return _call_openai_text(system, user, model, key)


async def run_cohort_analysis(
    user_prompt: str,
    calls: list[CohortCall],
    *,
    anonymize: bool = True,
    provider: str = "openai",
    api_key: str | None = None,
    model: str | None = None,
    ollama_base_url: str | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> str:
    if not calls:
        raise ValueError("No calls in cohort")

    def progress(**kwargs: Any) -> None:
        if on_progress:
            on_progress(kwargs)

    settings = get_settings()
    prov = (provider or "openai").lower()
    model_name = model or settings.openai_model

    progress(phase="llm", step="prepare", call_count=len(calls))
    dataset = _build_cohort_dataset(calls, anonymize=anonymize, provider=prov)
    total_chars = len(dataset) + len(user_prompt)

    if total_chars <= COHORT_SINGLE_SHOT_MAX_CHARS:
        progress(phase="llm", step="single", call_count=len(calls))
        user_msg = (
            f"Исследовательский вопрос:\n{user_prompt}\n\n"
            f"Датасет ({len(calls)} звонков):\n\n{dataset}\n\n"
            "Сформируй итоговый отчёт по всей выборке."
        )
        return _invoke_cohort_llm(
            COHORT_SYSTEM_PROMPT,
            user_msg,
            provider=prov,
            model=model_name,
            api_key=api_key,
            ollama_base_url=ollama_base_url,
        )

    batch_notes: list[str] = []
    batch_total = (len(calls) + COHORT_MAP_BATCH_SIZE - 1) // COHORT_MAP_BATCH_SIZE
    for i in range(0, len(calls), COHORT_MAP_BATCH_SIZE):
        batch = calls[i : i + COHORT_MAP_BATCH_SIZE]
        progress(
            phase="llm",
            step="map",
            batch=i // COHORT_MAP_BATCH_SIZE + 1,
            batch_total=batch_total,
            call_count=len(calls),
        )
        batch_data = _build_cohort_dataset(batch, anonymize=anonymize, provider=prov)
        map_user = (
            f"Исследовательский вопрос:\n{user_prompt}\n\n"
            f"Часть выборки (звонки {i + 1}–{i + len(batch)} из {len(calls)}):\n\n{batch_data}\n\n"
            "Дай промежуточные выводы по этой части: темы, паттерны, цитаты. Markdown."
        )
        note = _invoke_cohort_llm(
            COHORT_SYSTEM_PROMPT,
            map_user,
            provider=prov,
            model=model_name,
            api_key=api_key,
            ollama_base_url=ollama_base_url,
        )
        batch_notes.append(f"## Часть {i // COHORT_MAP_BATCH_SIZE + 1}\n\n{note}")

    progress(phase="llm", step="reduce", batch_total=batch_total, call_count=len(calls))
    reduce_user = (
        f"Исследовательский вопрос:\n{user_prompt}\n\n"
        f"Проанализировано {len(calls)} звонков в {len(batch_notes)} частях.\n\n"
        "Промежуточные выводы:\n\n"
        + "\n\n---\n\n".join(batch_notes)
        + "\n\nСформируй единый итоговый отчёт по всей выборке. Markdown."
    )
    return _invoke_cohort_llm(
        COHORT_SYSTEM_PROMPT,
        reduce_user,
        provider=prov,
        model=model_name,
        api_key=api_key,
        ollama_base_url=ollama_base_url,
    )
