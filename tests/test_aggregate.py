import json
from pathlib import Path

from daily_paper.aggregate import AggregatePipeline
from daily_paper.config import load_config


def _daily_report(report_date: str, title: str, paper_id: str, topic_key: str = "agents") -> dict:
    topic_counts = {"vla": 0, "world_models": 0, "multimodal_llm": 0, "agents": 0, "other_relevant": 0}
    topic_counts[topic_key] = 1
    return {
        "report_date": report_date,
        "statistics": {"selected_total": 1, "highlights_total": 1},
        "topic_counts": topic_counts,
        "highlight_papers": [
            {
                "paper_id": paper_id,
                "title": title,
                "primary_topic": "Agents",
                "method_tags": ["planning"],
                "application_tags": ["web agent"],
                "recommended_action": "read_now",
                "highlight_score": 4.1,
                "source_primary": "arXiv",
                "paper_url": "https://arxiv.org/abs/2604.00001",
                "code_url": None,
            }
        ],
        "paper_list_by_topic": {"Agents": []},
    }


def test_weekly_aggregate_smoke(tmp_path: Path) -> None:
    (tmp_path / "2026-04-13.json").write_text(json.dumps(_daily_report("2026-04-13", "Paper A", "arxiv-a")), encoding="utf-8")
    (tmp_path / "2026-04-14.json").write_text(json.dumps(_daily_report("2026-04-14", "Paper A", "arxiv-a")), encoding="utf-8")
    (tmp_path / "2026-04-15.json").write_text(json.dumps(_daily_report("2026-04-15", "Paper B", "arxiv-b")), encoding="utf-8")

    pipeline = AggregatePipeline(load_config())
    report = pipeline.aggregate_weekly(anchor_date=__import__("datetime").date(2026, 4, 14), input_dir=tmp_path)
    payload = report["json"]

    assert payload["statistics"]["reports_included"] == 3
    assert payload["statistics"]["unique_papers_total"] == 2
    assert payload["top_papers"][0]["paper_id"] == "arxiv-a"
    assert "Weekly Research Digest" in report["markdown"]

