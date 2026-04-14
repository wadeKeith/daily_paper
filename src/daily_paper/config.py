from __future__ import annotations

from pathlib import Path

import yaml

from daily_paper.models import LLMConfig, PipelineConfig, TopicProfile
from daily_paper.utils import repo_root


def default_config_path() -> Path:
    return repo_root() / "config" / "topics.yaml"


def load_config(config_path: str | Path | None = None) -> PipelineConfig:
    path = Path(config_path) if config_path else default_config_path()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    report = raw["report"]
    llm = raw.get("llm", {})
    aggregation = raw.get("aggregation", {})
    topics = [
        TopicProfile(
            id=topic["id"],
            name=topic["name"],
            summary_name=topic["summary_name"],
            query_terms=topic["query_terms"],
            high_keywords=topic["high_keywords"],
            medium_keywords=topic["medium_keywords"],
            method_tags=topic.get("method_tags", {}),
            application_tags=topic.get("application_tags", {}),
        )
        for topic in raw["topics"]
    ]
    return PipelineConfig(
        repo_name=report["repo_name"],
        pipeline_version=report["pipeline_version"],
        timezone=report["timezone"],
        lookback_days=int(report["lookback_days"]),
        highlight_limit=int(report["highlight_limit"]),
        selected_limit_per_topic=int(report["selected_limit_per_topic"]),
        other_relevant_limit=int(report["other_relevant_limit"]),
        arxiv_max_results_per_group=int(report["arxiv_max_results_per_group"]),
        arxiv_polite_delay_seconds=float(report["arxiv_polite_delay_seconds"]),
        huggingface_recent_papers_limit=int(report["huggingface_recent_papers_limit"]),
        huggingface_daily_papers_limit=int(report["huggingface_daily_papers_limit"]),
        user_agent=report["user_agent"],
        include_if=report["include_if"],
        exclude_if=report["exclude_if"],
        ranking_formula=report["ranking_formula"],
        ranking_scale=report["ranking_scale"],
        llm=LLMConfig(
            enabled=bool(llm.get("enabled", False)),
            provider=llm.get("provider", "openai_responses"),
            api_key_env=llm.get("api_key_env", "OPENAI_API_KEY"),
            api_base=llm.get("api_base", "https://api.openai.com/v1"),
            model=llm.get("model") or None,
            model_env=llm.get("model_env", "DAILY_PAPER_LLM_MODEL"),
            reasoning_effort=llm.get("reasoning_effort", "low"),
            timeout_seconds=int(llm.get("timeout_seconds", 90)),
            max_daily_highlights=int(llm.get("max_daily_highlights", 5)),
            max_aggregate_papers=int(llm.get("max_aggregate_papers", 12)),
        ),
        aggregation={
            "weekly_top_papers": int(aggregation.get("weekly_top_papers", 10)),
            "monthly_top_papers": int(aggregation.get("monthly_top_papers", 15)),
            "top_days_limit": int(aggregation.get("top_days_limit", 7)),
            "top_tags_limit": int(aggregation.get("top_tags_limit", 8)),
        },
        topics=topics,
        related_keywords=raw.get("related_keywords", {}).get("other_relevant", []),
    )
