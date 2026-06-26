from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.research_export import (
    build_research_markdown_export,
    research_export_filename,
)


def _study(**kwargs):
    defaults = {
        "id": 7,
        "title": "Жалобы клиентов",
        "prompt": "Какие основные жалобы?",
        "filters_json": {"date_from": "2026-05-01", "date_to": "2026-05-31"},
        "call_count": 2,
        "call_ids": [10, 11],
        "llm_model": "gpt-4o-mini",
        "report_markdown": "## Итог\n\nКлиенты недовольны сроками.",
        "created_at": datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
        "finished_at": datetime(2026, 5, 20, 12, 5, tzinfo=timezone.utc),
        "user": SimpleNamespace(full_name="Administrator"),
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_research_export_filename():
    name = research_export_filename(3, "Причины звонков!", ext="md")
    assert name.startswith("research-3-")
    assert name.endswith(".md")


def test_build_research_markdown_export_includes_sections():
    md = build_research_markdown_export(_study())
    assert "# Жалобы клиентов" in md
    assert "## Промпт" in md
    assert "## Отчёт" in md
    assert "Клиенты недовольны сроками." in md
    assert "от 2026-05-01" in md
    assert "#10, #11" in md
