from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class TopicProfile:
    id: str
    name: str
    summary_name: str
    query_terms: list[str]
    high_keywords: list[str]
    medium_keywords: list[str]
    method_tags: dict[str, list[str]]
    application_tags: dict[str, list[str]]


@dataclass(slots=True)
class LLMConfig:
    enabled: bool
    provider: str
    api_key_env: str
    api_base: str
    model: str | None
    model_env: str | None
    reasoning_effort: str | None
    timeout_seconds: int
    max_daily_highlights: int
    max_aggregate_papers: int


@dataclass(slots=True)
class PipelineConfig:
    repo_name: str
    pipeline_version: str
    timezone: str
    lookback_days: int
    highlight_limit: int
    selected_limit_per_topic: int
    other_relevant_limit: int
    arxiv_max_results_per_group: int
    arxiv_polite_delay_seconds: float
    huggingface_recent_papers_limit: int
    huggingface_daily_papers_limit: int
    user_agent: str
    include_if: list[str]
    exclude_if: list[str]
    ranking_formula: str
    ranking_scale: str
    llm: LLMConfig
    aggregation: dict[str, int]
    topics: list[TopicProfile]
    related_keywords: list[str]


@dataclass(slots=True)
class CandidatePaper:
    title: str
    authors: list[str]
    summary: str
    source_name: str
    source_alias: str
    source_aliases: list[str]
    paper_url: str
    pdf_url: str | None
    arxiv_id: str | None
    version: str | None
    hf_paper_url: str | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    primary_category: str | None = None
    categories: list[str] = field(default_factory=list)
    comment: str | None = None
    journal_ref: str | None = None
    doi: str | None = None
    code_url: str | None = None
    project_url: str | None = None
    model_url: str | None = None
    dataset_url: str | None = None
    demo_url: str | None = None
    institution_hint: str | None = None
    license_hint: str | None = None
    hf_upvotes: int | None = None
    hf_ai_summary: str | None = None
    hf_ai_keywords: list[str] = field(default_factory=list)
    submitted_on_daily_at: datetime | None = None
    query_groups: list[str] = field(default_factory=list)
    raw_source_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PaperRecord:
    paper_id: str
    title: str
    authors: list[str]
    first_author: str
    source_primary: str
    source_aliases: list[str]
    arxiv_id: str | None
    version: str | None
    hf_paper_url: str | None
    paper_url: str
    pdf_url: str | None
    project_url: str | None
    code_url: str | None
    model_url: str | None
    dataset_url: str | None
    demo_url: str | None
    published_at: datetime | None
    updated_at: datetime | None
    primary_category: str | None
    categories: list[str]
    institution_hint: str | None
    license_hint: str | None
    comment: str | None
    journal_ref: str | None
    doi: str | None
    summary: str
    topics: list[str] = field(default_factory=list)
    primary_topic: str = "Other Relevant"
    query_groups: list[str] = field(default_factory=list)
    method_tags: list[str] = field(default_factory=list)
    application_tags: list[str] = field(default_factory=list)
    one_line_summary: str = ""
    why_read_today: str = ""
    relevance_level: str = "medium"
    highlight_score: float = 0.0
    recommended_action: str = "track"
    topic_scores: dict[str, float] = field(default_factory=dict)
    structured_summary: dict[str, str] = field(default_factory=dict)
    novelty_points: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    relation_to_prior_work: str = ""
    domain_analysis: dict[str, Any] = field(default_factory=dict)
    reproducibility: dict[str, Any] = field(default_factory=dict)
    my_take: dict[str, str] = field(default_factory=dict)
    hf_upvotes: int | None = None
    hf_ai_summary: str | None = None
    hf_ai_keywords: list[str] = field(default_factory=list)
    submitted_on_daily_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("published_at", "updated_at", "submitted_on_daily_at"):
            if data[key]:
                data[key] = data[key].isoformat()
        return data
