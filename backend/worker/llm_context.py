import json
from dataclasses import dataclass

from sqlalchemy import select

from app.models import AutomationRule, Criterion, Scenario, Transcription
from app.services.call_utils import format_transcript_for_llm
from app.services.llm import analyze_transcript
from app.services.quality_settings import DEFAULT_TAXONOMY, parse_topics
from worker.settings_sync import get_setting_sync


def get_llm_kwargs(db) -> dict:
    provider = get_setting_sync(db, "llm_provider", "openai")
    api_key = get_setting_sync(db, "openai_api_key")
    if provider == "gemini":
        api_key = get_setting_sync(db, "gemini_api_key") or api_key
    return {
        "anonymize": get_setting_sync(db, "pii_anonymization", "true").lower() in ("1", "true", "yes"),
        "provider": provider,
        "api_key": api_key or None,
        "ollama_base_url": get_setting_sync(db, "ollama_base_url", "http://host.docker.internal:11434"),
    }


def resolve_scenario(db, call, scenario_id: int | None = None) -> Scenario | None:
    sid = scenario_id or call.scenario_id
    if not sid:
        rule = db.execute(select(AutomationRule).limit(1)).scalar_one_or_none()
        sid = rule.default_scenario_id if rule else None
    if sid:
        return db.get(Scenario, sid)
    return db.execute(select(Scenario).where(Scenario.is_active.is_(True)).limit(1)).scalar_one_or_none()


@dataclass
class PreparedLLMAnalysis:
    transcript: str
    scenario: Scenario
    criteria: list[Criterion]
    llm_kwargs: dict
    llm_model: str
    topics: list[str]
    scenario_id: int


def snapshot_scenario(scenario: Scenario) -> Scenario:
    return Scenario(
        id=scenario.id,
        name=scenario.name,
        system_prompt=scenario.system_prompt,
        llm_model=scenario.llm_model,
        is_active=scenario.is_active,
    )


def snapshot_criteria(criteria: list[Criterion]) -> list[Criterion]:
    return [
        Criterion(
            id=c.id,
            scenario_id=c.scenario_id,
            key=c.key,
            name=c.name,
            weight_percent=c.weight_percent,
            max_score=c.max_score,
            prompt=c.prompt,
            sort_order=c.sort_order,
        )
        for c in criteria
    ]


def prepare_llm_analysis(db, call, scenario_id: int | None = None) -> PreparedLLMAnalysis:
    """Load everything needed for LLM analysis. Close the session before calling the model."""
    trans = db.execute(
        select(Transcription)
        .where(Transcription.call_id == call.id)
        .order_by(Transcription.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    transcript = format_transcript_for_llm(
        trans.full_text if trans else None,
        trans.utterances if trans else None,
    )
    if not transcript:
        raise ValueError("No transcription")

    scenario = resolve_scenario(db, call, scenario_id)
    if not scenario:
        raise ValueError("No active scenario")

    criteria = list(
        db.execute(
            select(Criterion).where(Criterion.scenario_id == scenario.id).order_by(Criterion.sort_order)
        ).scalars()
    )
    llm_kwargs = get_llm_kwargs(db)
    llm_model = get_setting_sync(db, "llm_model", scenario.llm_model)
    topics = parse_topics(
        get_setting_sync(db, "call_topics", json.dumps(DEFAULT_TAXONOMY, ensure_ascii=False))
    )
    scenario_id_resolved = scenario.id

    return PreparedLLMAnalysis(
        transcript=transcript,
        scenario=snapshot_scenario(scenario),
        criteria=snapshot_criteria(criteria),
        llm_kwargs=llm_kwargs,
        llm_model=llm_model,
        topics=topics,
        scenario_id=scenario_id_resolved,
    )


def run_prepared_analysis(prepared: PreparedLLMAnalysis, *, strict: bool = False):
    import asyncio

    return asyncio.run(
        analyze_transcript(
            prepared.scenario,
            prepared.criteria,
            prepared.transcript,
            model=prepared.llm_model,
            topics=prepared.topics,
            strict=strict,
            **prepared.llm_kwargs,
        )
    )


def run_llm_analysis(db, call, scenario_id: int | None = None, *, strict: bool = False):
    """Load + run in the current session. Prefer prepare + run_prepared_analysis in workers."""
    return run_prepared_analysis(prepare_llm_analysis(db, call, scenario_id), strict=strict)
