import json

from sqlalchemy import select

from app.models import AutomationRule, Criterion, Scenario, Transcription
from app.services.llm import analyze_transcript
from app.services.quality_settings import DEFAULT_TAXONOMY, parse_topics
from worker.db import get_sync_session
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


def run_llm_analysis(db, call, scenario_id: int | None = None, *, strict: bool = False):
    import asyncio

    trans = db.execute(
        select(Transcription)
        .where(Transcription.call_id == call.id)
        .order_by(Transcription.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if not trans or not trans.full_text:
        raise ValueError("No transcription")

    scenario = resolve_scenario(db, call, scenario_id)
    if not scenario:
        raise ValueError("No active scenario")

    criteria = list(
        db.execute(
            select(Criterion).where(Criterion.scenario_id == scenario.id).order_by(Criterion.sort_order)
        ).scalars()
    )
    kwargs = get_llm_kwargs(db)
    llm_model = get_setting_sync(db, "llm_model", scenario.llm_model)
    topics = parse_topics(
        get_setting_sync(db, "call_topics", json.dumps(DEFAULT_TAXONOMY, ensure_ascii=False))
    )
    return asyncio.run(
        analyze_transcript(
            scenario,
            criteria,
            trans.full_text,
            model=llm_model,
            topics=topics,
            strict=strict,
            **kwargs,
        )
    )
