import json
import logging
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import httpx
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import get_settings
from app.core.retry import backoff_seconds
from app.models import Criterion, Scenario
from app.services.pii import prepare_text_for_llm
from app.services.quality_settings import UNCLASSIFIED_TOPIC

logger = logging.getLogger(__name__)


class LLMUnavailableError(RuntimeError):
    """The LLM produced no usable analysis (no key, provider down, invalid JSON).

    Raised only in strict mode so the pipeline can mark the call as failed instead
    of storing a placeholder verdict that looks like a real score.
    """


def _llm_retries() -> int:
    return get_settings().llm_max_retries
# Must match AnalysisResult.call_outcome column width.
CALL_OUTCOME_MAX_LEN = 100
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
    # Models sometimes answer with a whole sentence instead of a short label;
    # clamp to the DB column width so persisting the analysis cannot fail.
    call_outcome: str = Field(default="", max_length=CALL_OUTCOME_MAX_LEN)
    topic: str = ""
    criteria_results: dict[str, CriterionResult]

    @field_validator("call_outcome", mode="before")
    @classmethod
    def _clamp_call_outcome(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)[:CALL_OUTCOME_MAX_LEN]


def _allowed_topics(topics: list[str] | None) -> list[str]:
    clean = [t.strip() for t in (topics or []) if t and t.strip()]
    if UNCLASSIFIED_TOPIC not in clean:
        clean.append(UNCLASSIFIED_TOPIC)
    return clean


def normalize_topic(raw: str | None, topics: list[str] | None) -> str:
    allowed = _allowed_topics(topics)
    value = (raw or "").strip()
    if not value:
        return UNCLASSIFIED_TOPIC
    for t in allowed:
        if t.lower() == value.lower():
            return t
    return UNCLASSIFIED_TOPIC


def _criterion_result_schema(criterion: Criterion) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": criterion.max_score},
            "passed": {"type": "boolean"},
            "comment": {"type": "string"},
            "status": {"type": "string", "enum": ["completed", "not_applicable"]},
        },
        "required": ["score", "passed", "comment", "status"],
        "additionalProperties": False,
    }


def _analysis_json_schema(criteria: list[Criterion], topics: list[str] | None = None) -> dict[str, Any]:
    """JSON Schema for OpenAI strict structured output (all objects need additionalProperties: false)."""
    criterion_props = {c.key: _criterion_result_schema(c) for c in criteria}
    topic_schema: dict[str, Any] = {"type": "string"}
    allowed = _allowed_topics(topics)
    if allowed:
        topic_schema["enum"] = allowed
    return {
        "type": "object",
        "properties": {
            "total_score": {"type": "integer"},
            "is_violation": {"type": "boolean"},
            "summary": {"type": "string"},
            "client_pains": {"type": "string"},
            "call_outcome": {"type": "string"},
            "topic": topic_schema,
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
            "topic",
            "criteria_results",
        ],
        "additionalProperties": False,
    }


def _build_prompt(
    scenario: Scenario, criteria: list[Criterion], transcript: str, topics: list[str] | None = None
) -> str:
    criteria_block = "\n".join(
        f'- "{c.key}" ({c.name}, max {c.max_score}, weight {c.weight_percent}%): {c.prompt}'
        for c in criteria
    )
    topics_block = ""
    allowed = _allowed_topics(topics)
    if allowed:
        topic_list = "\n".join(f"- {t}" for t in allowed)
        topics_block = (
            "\n\nОпредели тему звонка. Выбери РОВНО ОДНУ тему из списка "
            f'(поле "topic"). Если ни одна не подходит — верни "{UNCLASSIFIED_TOPIC}".\n'
            f"Список тем:\n{topic_list}\n"
        )
    return f"""{scenario.system_prompt}

Оцени транскрипт разговора колл-центра. Ответ — только JSON.
Реплики помечены ролями [agent] (оператор) и [client] (клиент) и таймкодом; учитывай роли при оценке критериев.

Критерии:
{criteria_block}
{topics_block}
Транскрипт:
{transcript}
"""


def _call_openai(
    prompt: str,
    model: str,
    api_key: str,
    criteria: list[Criterion],
    topics: list[str] | None = None,
) -> dict[str, Any]:
    client = OpenAI(api_key=api_key, timeout=get_settings().llm_timeout_sec)
    messages = [
        {
            "role": "system",
            "content": "Ты аналитик качества колл-центра. Отвечай строго в формате JSON по схеме.",
        },
        {"role": "user", "content": prompt},
    ]
    schema = _analysis_json_schema(criteria, topics)
    response = client.responses.create(
        model=model,
        input=messages,
        text={
            "format": {
                "type": "json_schema",
                "name": "call_analysis",
                "strict": True,
                "schema": schema,
            },
        },
        store=False,
    )
    raw = response.output_text or "{}"
    return json.loads(raw)


def _call_ollama(prompt: str, model: str, base_url: str) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/api/chat"
    with httpx.Client(timeout=get_settings().llm_timeout_long_sec) as client:
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
    topics: list[str] | None = None,
    strict: bool = True,
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

    prompt = _build_prompt(scenario_copy, criteria, text, topics)
    last_error: Exception | None = None
    retries = _llm_retries()

    for attempt in range(retries):
        try:
            if prov == "local" or prov == "ollama":
                base = ollama_base_url or await _get_setting_fallback(
                    "ollama_base_url", get_settings().ollama_base_url
                )
                data = _call_ollama(prompt, model_name, base)
            elif prov == "gemini":
                data = await _call_gemini(prompt, model_name, api_key)
            else:
                key = api_key or settings.openai_api_key
                if not key:
                    raise LLMUnavailableError(
                        "Не задан ключ OpenAI — укажите его в «Настройки → Модели и AI»"
                    )
                data = _call_openai(prompt, model_name, key, criteria, topics)
            output = AnalysisOutput.model_validate(data)
            _validate_and_finalize_analysis(output, criteria)
            output.topic = normalize_topic(output.topic, topics)
            return output
        except LLMUnavailableError:
            raise
        except (json.JSONDecodeError, ValidationError, Exception) as e:
            last_error = e
            logger.warning("LLM attempt %s failed: %s", attempt + 1, e)
            if attempt < retries - 1:
                await asyncio.sleep(backoff_seconds(attempt))
            prompt = prompt + "\n\n(Предыдущий ответ невалиден. Верни корректный JSON.)"

    logger.error("LLM failed after retries: %s", last_error)
    raise LLMUnavailableError("LLM не вернул корректный ответ")


def _validate_and_finalize_analysis(
    output: AnalysisOutput, criteria: list[Criterion]
) -> None:
    expected = {criterion.key for criterion in criteria}
    actual = set(output.criteria_results)
    if actual != expected:
        raise ValueError("LLM response criteria do not match the scenario")

    weighted_total = 0.0
    for criterion in criteria:
        result = output.criteria_results[criterion.key]
        if result.score < 0 or result.score > criterion.max_score:
            raise ValueError(f"Criterion {criterion.key} score is out of range")
        if result.status == "not_applicable":
            result.score = 0
            result.passed = False
            continue
        if criterion.max_score > 0:
            weighted_total += (
                result.score / criterion.max_score * criterion.weight_percent
            )
    output.total_score = min(100, max(0, round(weighted_total)))


MAX_TOPIC_TRANSCRIPT_CHARS = 12_000


def _classify_topic_openai(prompt: str, model: str, api_key: str, topics: list[str]) -> str:
    client = OpenAI(api_key=api_key, timeout=45.0)
    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": "Ты классифицируешь звонки колл-центра по теме. Отвечай строго JSON."},
            {"role": "user", "content": prompt},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "topic_classification",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"topic": {"type": "string", "enum": _allowed_topics(topics)}},
                    "required": ["topic"],
                    "additionalProperties": False,
                },
            }
        },
        store=False,
    )
    raw = response.output_text or "{}"
    return json.loads(raw).get("topic", "")


def _build_topic_prompt(transcript: str, topics: list[str]) -> str:
    topic_list = "\n".join(f"- {t}" for t in _allowed_topics(topics))
    return (
        "Определи тему звонка. Выбери РОВНО ОДНУ тему из списка. "
        f'Если ни одна не подходит — верни "{UNCLASSIFIED_TOPIC}".\n\n'
        f"Список тем:\n{topic_list}\n\n"
        f"Транскрипт:\n{transcript}\n\n"
        'Ответ строго JSON вида {"topic": "<тема>"}.'
    )


async def classify_topic(
    transcript: str,
    topics: list[str],
    *,
    anonymize: bool = True,
    provider: str = "openai",
    api_key: str | None = None,
    model: str | None = None,
    ollama_base_url: str | None = None,
) -> str:
    """Lightweight topic-only classification (used for backfill of existing calls)."""
    settings = get_settings()
    prov = (provider or "openai").lower()
    model_name = model or settings.openai_model
    try:
        text = prepare_text_for_llm(
            transcript[:MAX_TOPIC_TRANSCRIPT_CHARS],
            provider=prov,
            anonymize_enabled=anonymize,
            require_anonymization_for_cloud=True,
        )
    except Exception as e:
        logger.warning("Topic classification skipped (PII prep failed): %s", e)
        return UNCLASSIFIED_TOPIC
    prompt = _build_topic_prompt(text, topics)
    try:
        if prov in ("local", "ollama"):
            base = ollama_base_url or "http://host.docker.internal:11434"
            data = _call_ollama(prompt, model_name, base)
            raw = data.get("topic", "") if isinstance(data, dict) else ""
        elif prov == "gemini":
            data = await _call_gemini(prompt, model_name, api_key)
            raw = data.get("topic", "") if isinstance(data, dict) else ""
        else:
            key = api_key or settings.openai_api_key
            if not key:
                return UNCLASSIFIED_TOPIC
            raw = _classify_topic_openai(prompt, model_name, key, topics)
    except Exception as e:
        logger.warning("Topic classification failed: %s", e)
        return UNCLASSIFIED_TOPIC
    return normalize_topic(raw, topics)


async def _get_setting_fallback(key: str, default: str) -> str:
    return default


async def _call_gemini(prompt: str, model: str, api_key: str | None) -> dict[str, Any]:
    key = api_key or ""
    if not key:
        raise ValueError("Gemini API key not configured")
    url = f"{get_settings().gemini_api_url.rstrip('/')}/models/{model}:generateContent"
    with httpx.Client(timeout=get_settings().llm_timeout_long_sec) as client:
        r = client.post(
            url,
            headers={"x-goog-api-key": key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
        )
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)


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
    timeout: float | None = None,
) -> str:
    client = OpenAI(api_key=api_key, timeout=timeout or get_settings().llm_timeout_cohort_sec)
    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        store=False,
    )
    return (response.output_text or "").strip()


def _call_ollama_text(system: str, user: str, model: str, base_url: str) -> str:
    url = base_url.rstrip("/") + "/api/chat"
    with httpx.Client(timeout=get_settings().llm_timeout_cohort_sec) as client:
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
    url = f"{get_settings().gemini_api_url.rstrip('/')}/models/{model}:generateContent"
    prompt = f"{system}\n\n{user}"
    with httpx.Client(timeout=get_settings().llm_timeout_cohort_sec) as client:
        r = client.post(
            url,
            headers={"x-goog-api-key": key},
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
