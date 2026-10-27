import pytest

from app.models import Criterion, Scenario
from app.services.llm import (
    AnalysisOutput,
    CriterionResult,
    LLMUnavailableError,
    _validate_and_finalize_analysis,
    analyze_transcript,
)


def _criterion(key: str = "greeting") -> Criterion:
    return Criterion(
        key=key,
        name="Greeting",
        max_score=10,
        weight_percent=20,
        prompt="Check greeting",
        sort_order=0,
    )


def test_total_score_is_computed_from_validated_criteria():
    criterion = _criterion()
    output = AnalysisOutput(
        total_score=99,
        criteria_results={
            criterion.key: CriterionResult(
                score=5, passed=True, comment="partial", status="completed"
            )
        },
    )

    _validate_and_finalize_analysis(output, [criterion])

    assert output.total_score == 10


def test_out_of_range_criterion_score_is_rejected():
    criterion = _criterion()
    output = AnalysisOutput(
        total_score=100,
        criteria_results={
            criterion.key: CriterionResult(
                score=11, passed=True, comment="invalid", status="completed"
            )
        },
    )

    with pytest.raises(ValueError, match="out of range"):
        _validate_and_finalize_analysis(output, [criterion])


@pytest.mark.asyncio
async def test_missing_cloud_key_fails_closed(monkeypatch):
    monkeypatch.setattr("app.services.llm._llm_retries", lambda: 1)
    from app.services.llm import get_settings

    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    scenario = Scenario(
        id=1,
        name="QA",
        system_prompt="Evaluate",
        llm_model="gpt-4o-mini",
    )

    with pytest.raises(LLMUnavailableError):
        await analyze_transcript(
            scenario,
            [_criterion()],
            "[agent] hello",
            provider="openai",
            api_key="",
        )
