from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date, datetime
from typing import Any

from daily_paper.classification import TopicClassifier
from daily_paper.env import resolve_model_name
from daily_paper.llm import OpenAIResponsesSummarizer
from daily_paper.models import CandidatePaper, PaperRecord, PipelineConfig
from daily_paper.render import render_markdown
from daily_paper.sources.arxiv import ArxivClient
from daily_paper.sources.huggingface import HuggingFacePapersClient
from daily_paper.utils import (
    clip_text,
    extract_arxiv_id,
    first_non_empty,
    git_commit_hash,
    log_score,
    normalize_title,
    report_window,
    safe_percentage,
    slugify,
    split_sentences,
    within_window,
)


SOURCE_PRIORITY = {"arXiv": 3, "HuggingFace Papers": 2}
TOPIC_ID_TO_NAME = {
    "vla": "VLA",
    "world_models": "World Models",
    "multimodal_llm": "Multimodal LLMs",
    "agents": "Agents",
}
TOPIC_NAME_TO_ID = {value: key for key, value in TOPIC_ID_TO_NAME.items()}


class DigestPipeline:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.classifier = TopicClassifier(config)

    def generate(self, report_date: date, timezone: str | None = None) -> dict[str, Any]:
        report_timezone = timezone or self.config.timezone
        window_start, window_end = report_window(report_date, report_timezone, self.config.lookback_days)
        crawl_errors: list[str] = []
        parsing_warnings: list[str] = []
        filtered_out: list[dict[str, str]] = []
        deduplication_log: list[str] = []
        llm_warnings: list[str] = []

        candidates = self._collect_candidates(report_date, crawl_errors)
        raw_candidates_total = len(candidates)

        in_window: list[CandidatePaper] = []
        for candidate in candidates:
            reason = self._filter_by_window(candidate, window_start, window_end)
            if reason:
                filtered_out.append({"title": candidate.title, "reason": reason})
                continue
            in_window.append(candidate)

        merged = self._merge_candidates(in_window, deduplication_log)
        deduplicated_total = len(merged)

        relevant_records: list[PaperRecord] = []
        for candidate in merged.values():
            record = self._candidate_to_record(candidate)
            classification = self.classifier.classify(record.title, record.summary, record.query_groups)
            if not classification.include:
                filtered_out.append({"title": record.title, "reason": "Classifier marked it as out of scope"})
                continue
            record.topics = classification.matched_topics
            record.primary_topic = classification.primary_topic
            record.method_tags = classification.method_tags
            record.application_tags = classification.application_tags
            record.topic_scores = classification.topic_scores
            relevant_records.append(record)

        selected_records = self._limit_records(relevant_records, filtered_out, use_preliminary=True)

        self._enrich_records_with_hf(selected_records, crawl_errors)
        for record in selected_records:
            self._populate_derived_fields(record, window_start, window_end)
            if not record.authors:
                parsing_warnings.append(f"{record.title} — missing authors")
            if not record.paper_url:
                parsing_warnings.append(f"{record.title} — missing paper_url")

        selected_records.sort(key=lambda item: item.highlight_score, reverse=True)
        highlights = selected_records[: self.config.highlight_limit]
        highlight_ids = {paper.paper_id for paper in highlights}
        papers_by_topic = self._group_by_topic(selected_records)

        report_json = self._build_report_json(
            report_date=report_date,
            timezone=report_timezone,
            window_start=window_start,
            window_end=window_end,
            raw_candidates_total=raw_candidates_total,
            deduplicated_total=deduplicated_total,
            selected_records=selected_records,
            highlights=highlights,
            papers_by_topic=papers_by_topic,
            highlight_ids=highlight_ids,
            filtered_out=filtered_out,
            deduplication_log=deduplication_log,
            crawl_errors=crawl_errors,
            parsing_warnings=parsing_warnings,
            llm_warnings=llm_warnings,
        )
        self._maybe_llm_enhance_daily_report(report_json, llm_warnings)
        markdown = render_markdown(report_json)
        return {"markdown": markdown, "json": report_json}

    def _collect_candidates(self, report_date: date, crawl_errors: list[str]) -> list[CandidatePaper]:
        arxiv = ArxivClient(
            user_agent=self.config.user_agent,
            polite_delay_seconds=self.config.arxiv_polite_delay_seconds,
        )
        hf = HuggingFacePapersClient(user_agent=self.config.user_agent)
        items: list[CandidatePaper] = []
        try:
            for topic in self.config.topics:
                try:
                    items.extend(arxiv.search_topic(topic, max_results=self.config.arxiv_max_results_per_group))
                except Exception as exc:  # noqa: BLE001
                    crawl_errors.append(f"arXiv / {topic.name} — {exc}")
            try:
                items.extend(hf.list_recent_papers(limit=self.config.huggingface_recent_papers_limit))
            except Exception as exc:  # noqa: BLE001
                crawl_errors.append(f"HuggingFace Papers / Recent — {exc}")
            for target in (report_date, report_date.fromordinal(report_date.toordinal() - 1)):
                try:
                    items.extend(hf.list_daily_papers(target, limit=self.config.huggingface_daily_papers_limit))
                except Exception as exc:  # noqa: BLE001
                    crawl_errors.append(f"HuggingFace Papers / Daily Papers / {target.isoformat()} — {exc}")
        finally:
            arxiv.close()
            hf.close()
        return items

    def _filter_by_window(self, candidate: CandidatePaper, window_start: datetime, window_end: datetime) -> str | None:
        if candidate.source_name == "arXiv":
            if within_window(candidate.published_at, window_start, window_end) or within_window(candidate.updated_at, window_start, window_end):
                return None
            return "Outside crawl window for arXiv published/updated timestamps"
        if "Daily Papers" in candidate.source_alias:
            if within_window(candidate.submitted_on_daily_at, window_start, window_end) or within_window(candidate.published_at, window_start, window_end):
                return None
            return "Outside crawl window for HuggingFace Daily Papers"
        if within_window(candidate.published_at, window_start, window_end):
            return None
        return "Outside crawl window for HuggingFace recent paper list"

    def _merge_candidates(self, candidates: list[CandidatePaper], deduplication_log: list[str]) -> dict[str, CandidatePaper]:
        merged: dict[str, CandidatePaper] = {}
        for candidate in candidates:
            key = self._candidate_key(candidate)
            if key not in merged:
                merged[key] = candidate
                continue
            before = merged[key]
            merged[key] = self._combine_candidate(before, candidate)
            deduplication_log.append(
                f"{before.title} @ {before.source_alias} == {candidate.title} @ {candidate.source_alias} → merged into {merged[key].arxiv_id or merged[key].title}"
            )
        return merged

    def _candidate_key(self, candidate: CandidatePaper) -> str:
        if candidate.arxiv_id:
            return f"arxiv:{candidate.arxiv_id}"
        author = candidate.authors[0] if candidate.authors else "unknown"
        published = candidate.published_at.date().isoformat() if candidate.published_at else "unknown"
        return f"title:{normalize_title(candidate.title)}::{normalize_title(author)}::{published}"

    def _combine_candidate(self, left: CandidatePaper, right: CandidatePaper) -> CandidatePaper:
        preferred, secondary = (left, right)
        if SOURCE_PRIORITY.get(right.source_name, 0) > SOURCE_PRIORITY.get(left.source_name, 0):
            preferred, secondary = right, left
        combined = replace(preferred)
        combined.source_alias = preferred.source_alias
        combined.source_aliases = sorted(set(left.source_aliases + right.source_aliases))
        combined.query_groups = sorted(set(left.query_groups + right.query_groups))
        combined.categories = sorted(set(left.categories + right.categories))
        combined.authors = preferred.authors or secondary.authors
        combined.summary = preferred.summary if len(preferred.summary) >= len(secondary.summary) else secondary.summary
        combined.paper_url = preferred.paper_url or secondary.paper_url
        combined.pdf_url = preferred.pdf_url or secondary.pdf_url
        combined.hf_paper_url = preferred.hf_paper_url or secondary.hf_paper_url
        combined.project_url = preferred.project_url or secondary.project_url
        combined.code_url = preferred.code_url or secondary.code_url
        combined.model_url = preferred.model_url or secondary.model_url
        combined.dataset_url = preferred.dataset_url or secondary.dataset_url
        combined.demo_url = preferred.demo_url or secondary.demo_url
        combined.comment = preferred.comment or secondary.comment
        combined.journal_ref = preferred.journal_ref or secondary.journal_ref
        combined.doi = preferred.doi or secondary.doi
        combined.primary_category = preferred.primary_category or secondary.primary_category
        combined.published_at = min(
            [value for value in (left.published_at, right.published_at) if value],
            default=preferred.published_at,
        )
        combined.updated_at = max(
            [value for value in (left.updated_at, right.updated_at) if value],
            default=preferred.updated_at,
        )
        combined.hf_upvotes = max(value for value in (left.hf_upvotes, right.hf_upvotes) if value is not None) if any(
            value is not None for value in (left.hf_upvotes, right.hf_upvotes)
        ) else None
        combined.hf_ai_summary = preferred.hf_ai_summary or secondary.hf_ai_summary
        combined.hf_ai_keywords = sorted(set(left.hf_ai_keywords + right.hf_ai_keywords))
        combined.submitted_on_daily_at = max(
            [value for value in (left.submitted_on_daily_at, right.submitted_on_daily_at) if value],
            default=preferred.submitted_on_daily_at,
        )
        combined.raw_source_metadata = {**secondary.raw_source_metadata, **preferred.raw_source_metadata}
        return combined

    def _candidate_to_record(self, candidate: CandidatePaper) -> PaperRecord:
        paper_id = f"arxiv-{candidate.arxiv_id}" if candidate.arxiv_id else slugify(candidate.title)
        return PaperRecord(
            paper_id=paper_id,
            title=candidate.title,
            authors=candidate.authors,
            first_author=candidate.authors[0] if candidate.authors else "Unknown",
            source_primary=candidate.source_name,
            source_aliases=candidate.source_aliases,
            arxiv_id=candidate.arxiv_id,
            version=candidate.version,
            hf_paper_url=candidate.hf_paper_url,
            paper_url=candidate.paper_url,
            pdf_url=candidate.pdf_url,
            project_url=candidate.project_url,
            code_url=candidate.code_url,
            model_url=candidate.model_url,
            dataset_url=candidate.dataset_url,
            demo_url=candidate.demo_url,
            published_at=candidate.published_at,
            updated_at=candidate.updated_at,
            primary_category=candidate.primary_category,
            categories=candidate.categories,
            institution_hint=candidate.institution_hint,
            license_hint=candidate.license_hint,
            comment=candidate.comment,
            journal_ref=candidate.journal_ref,
            doi=candidate.doi,
            summary=candidate.summary,
            query_groups=candidate.query_groups,
            hf_upvotes=candidate.hf_upvotes,
            hf_ai_summary=candidate.hf_ai_summary,
            hf_ai_keywords=candidate.hf_ai_keywords,
            submitted_on_daily_at=candidate.submitted_on_daily_at,
        )

    def _enrich_records_with_hf(self, records: list[PaperRecord], crawl_errors: list[str]) -> None:
        hf = HuggingFacePapersClient(user_agent=self.config.user_agent)
        try:
            for record in records:
                if not record.arxiv_id:
                    continue
                try:
                    detail = hf.get_paper_detail(record.arxiv_id)
                    repos = hf.get_linked_repos(record.arxiv_id)
                    self._merge_hf_detail(record, detail, repos)
                except Exception as exc:  # noqa: BLE001
                    crawl_errors.append(f"HuggingFace enrichment / {record.arxiv_id} — {exc}")
        finally:
            hf.close()

    def _merge_hf_detail(self, record: PaperRecord, detail: dict | None, repos: dict | None) -> None:
        if detail:
            record.hf_paper_url = record.hf_paper_url or f"https://huggingface.co/papers/{record.arxiv_id}"
            record.code_url = record.code_url or detail.get("githubRepo")
            record.project_url = record.project_url or detail.get("projectPage")
            record.hf_upvotes = detail.get("upvotes", record.hf_upvotes)
            record.hf_ai_summary = record.hf_ai_summary or detail.get("ai_summary")
            record.hf_ai_keywords = sorted(set(record.hf_ai_keywords + detail.get("ai_keywords", [])))
            submitted_on_daily_at = detail.get("submittedOnDailyAt")
            if submitted_on_daily_at and not record.submitted_on_daily_at:
                from daily_paper.utils import parse_iso_datetime

                record.submitted_on_daily_at = parse_iso_datetime(submitted_on_daily_at)
        if repos:
            model = self._best_repo(repos.get("models", []))
            dataset = self._best_repo(repos.get("datasets", []))
            space = self._best_repo(repos.get("spaces", []))
            record.model_url = record.model_url or self._repo_url("model", model)
            record.dataset_url = record.dataset_url or self._repo_url("dataset", dataset)
            record.demo_url = record.demo_url or self._repo_url("space", space)
            if not record.license_hint:
                record.license_hint = first_non_empty(
                    [self._license_from_repo(repo) for repo in (model, dataset, space)],
                    fallback=None,
                )

    @staticmethod
    def _best_repo(repos: list[dict]) -> dict | None:
        if not repos:
            return None
        return max(repos, key=lambda repo: (repo.get("likes", 0), repo.get("downloads", 0)))

    @staticmethod
    def _repo_url(repo_type: str, repo: dict | None) -> str | None:
        if not repo:
            return None
        repo_id = repo.get("id")
        if not repo_id:
            return None
        if repo_type == "dataset":
            return f"https://huggingface.co/datasets/{repo_id}"
        if repo_type == "space":
            return f"https://huggingface.co/spaces/{repo_id}"
        return f"https://huggingface.co/{repo_id}"

    @staticmethod
    def _license_from_repo(repo: dict | None) -> str | None:
        if not repo:
            return None
        for tag in repo.get("tags", []):
            if tag.startswith("license:"):
                return tag.split(":", 1)[1]
        return None

    def _populate_derived_fields(self, record: PaperRecord, window_start: datetime, window_end: datetime) -> None:
        topic_relevance = max(record.topic_scores.values(), default=0.0)
        novelty = self._score_novelty(record, window_end)
        evidence = self._score_evidence(record)
        resource_readiness = self._score_resource_readiness(record)
        discussion_value = self._score_discussion_value(record)
        record.highlight_score = round(
            0.35 * topic_relevance
            + 0.20 * novelty
            + 0.20 * evidence
            + 0.15 * resource_readiness
            + 0.10 * discussion_value,
            2,
        )
        record.relevance_level = self._relevance_level(topic_relevance)
        record.one_line_summary = clip_text(record.hf_ai_summary or self._first_sentence(record.summary) or record.title, 220)
        record.why_read_today = self._why_read_today(record, window_start, window_end)
        record.recommended_action = self._recommended_action(record)
        record.structured_summary = self._build_structured_summary(record)
        record.novelty_points = self._build_novelty_points(record)
        record.strengths = self._build_strengths(record)
        record.weaknesses = self._build_weaknesses(record)
        record.assumptions = self._build_assumptions(record)
        record.risks = self._build_risks(record)
        record.open_questions = self._build_open_questions(record)
        record.relation_to_prior_work = self._relation_to_prior_work(record)
        record.domain_analysis = self._build_domain_analysis(record)
        record.reproducibility = self._build_reproducibility(record)
        record.my_take = self._build_my_take(record)

    def _score_novelty(self, record: PaperRecord, window_end: datetime) -> float:
        if not record.published_at:
            return 2.5
        delta_days = abs((window_end.date() - record.published_at.date()).days)
        if delta_days == 0:
            return 5.0
        if delta_days == 1:
            return 4.3
        if delta_days <= 3:
            return 3.5
        return 2.5

    def _score_evidence(self, record: PaperRecord) -> float:
        text = f"{record.title} {record.summary}".casefold()
        score = 1.5
        if any(keyword in text for keyword in ("benchmark", "benchmarks", "evaluation", "experiments", "trial", "results")):
            score += 1.4
        if any(keyword in text for keyword in ("outperform", "improve", "achieve", "demonstrate", "show")):
            score += 1.0
        if any(keyword in text for keyword in ("real robot", "real-world", "simulator", "simulation")):
            score += 0.8
        if any(char.isdigit() for char in record.summary):
            score += 0.4
        return min(5.0, round(score, 2))

    def _score_resource_readiness(self, record: PaperRecord) -> float:
        score = 1.0
        for url in (record.code_url, record.project_url, record.model_url, record.dataset_url, record.demo_url):
            if url:
                score += 0.9
        return min(5.0, round(score, 2))

    def _score_discussion_value(self, record: PaperRecord) -> float:
        score = log_score(record.hf_upvotes)
        if record.hf_ai_summary:
            score += 0.3
        if record.submitted_on_daily_at:
            score += 0.3
        return min(5.0, round(score, 2))

    @staticmethod
    def _relevance_level(score: float) -> str:
        if score >= 4.2:
            return "direct"
        if score >= 3.2:
            return "high"
        if score >= 2.2:
            return "medium"
        return "peripheral"

    def _recommended_action(self, record: PaperRecord) -> str:
        if record.highlight_score >= 3.8:
            return "read_now"
        if record.highlight_score >= 3.4 and record.code_url:
            return "reproduce"
        if record.highlight_score >= 2.7:
            return "track"
        return "ignore"

    @staticmethod
    def _first_sentence(text: str) -> str:
        return split_sentences(text, limit=1)[0] if split_sentences(text, limit=1) else ""

    def _why_read_today(self, record: PaperRecord, window_start: datetime, window_end: datetime) -> str:
        parts = [f"它直接落在 {record.primary_topic} 方向"]
        if record.code_url or record.model_url or record.dataset_url or record.demo_url:
            parts.append("并且已经能追踪到开源资源")
        if record.published_at and within_window(record.published_at, window_start, window_end):
            parts.append("属于当前统计窗口内的新条目")
        if record.highlight_score >= 4.0:
            parts.append("信号强，适合优先精读")
        return "，".join(parts) + "。"

    def _build_structured_summary(self, record: PaperRecord) -> dict[str, str]:
        sentences = split_sentences(record.summary)
        problem = self._find_sentence(sentences, ("address", "study", "focus", "goal", "problem")) or self._first_sentence(record.summary)
        motivation = self._find_sentence(sentences, ("however", "challenge", "bottleneck", "limited", "motivation")) or (
            sentences[1] if len(sentences) > 1 else "摘要没有明确写出动机层面的细节。"
        )
        core_idea = self._find_sentence(sentences, ("we propose", "we present", "we introduce", "our approach", "framework")) or problem
        method = self._find_sentence(sentences, ("framework", "method", "approach", "architecture", "pipeline")) or core_idea
        training = self._find_sentence(sentences, ("train", "fine-tune", "pretrain", "pre-train", "reinforcement learning", "distill")) or "摘要未明确说明训练细节。"
        inference = self._find_sentence(sentences, ("inference", "test time", "at test time", "deployment", "rollout")) or "摘要未明确描述推理阶段流程。"
        evaluation = self._find_sentence(sentences, ("benchmark", "experiment", "evaluation", "trial", "simulator", "real robot")) or "摘要只给出了有限的评测线索。"
        main_results = self._find_sentence(sentences, ("outperform", "improve", "achieve", "demonstrate", "show")) or (sentences[-1] if sentences else record.title)
        claim = main_results or core_idea
        return {
            "problem": clip_text(problem, 280),
            "motivation": clip_text(motivation, 280),
            "core_idea": clip_text(core_idea, 280),
            "method": clip_text(method, 280),
            "training": clip_text(training, 280),
            "inference": clip_text(inference, 280),
            "evaluation": clip_text(evaluation, 280),
            "main_results": clip_text(main_results, 280),
            "claim": clip_text(claim, 280),
        }

    @staticmethod
    def _find_sentence(sentences: list[str], keywords: tuple[str, ...]) -> str | None:
        for sentence in sentences:
            lowered = sentence.casefold()
            if any(keyword in lowered for keyword in keywords):
                return sentence
        return None

    def _build_novelty_points(self, record: PaperRecord) -> list[str]:
        items = [f"主线聚焦在 {record.primary_topic}，并给出了相对明确的方法叙述。"]
        if record.method_tags:
            items.append(f"方法标签里最显眼的是：{', '.join(record.method_tags[:3])}。")
        if record.code_url or record.model_url or record.dataset_url or record.demo_url:
            items.append("配套资源已有公开线索，后续做 related work / reproduction 会更顺。")
        return items[:2]

    def _build_strengths(self, record: PaperRecord) -> list[str]:
        strengths = ["标题和摘要都能清楚定位到研究问题。"]
        if any(keyword in record.summary.casefold() for keyword in ("benchmark", "evaluation", "experiment", "real robot", "simulator")):
            strengths.append("摘要里明确给出了评测或实验设置。")
        if record.code_url or record.model_url or record.dataset_url or record.demo_url:
            strengths.append("存在可继续追踪的开源资源。")
        return strengths[:2]

    def _build_weaknesses(self, record: PaperRecord) -> list[str]:
        weaknesses = []
        if not (record.code_url or record.model_url or record.dataset_url or record.demo_url):
            weaknesses.append("当前还看不到足够完整的开源 artifact。")
        if "real robot" not in record.summary.casefold() and record.primary_topic == "VLA":
            weaknesses.append("摘要没有明显展示真实机器人验证。")
        if len(split_sentences(record.summary)) < 3:
            weaknesses.append("摘要信息密度有限，很多判断仍需通读正文。")
        return weaknesses[:2] or ["摘要无法支撑太细的结论，需要正文补充。"]

    def _build_assumptions(self, record: PaperRecord) -> list[str]:
        topic = record.primary_topic
        if topic == "VLA":
            return ["默认任务分布、机器人形态和观测设置与实验环境接近。"]
        if topic == "World Models":
            return ["默认 learned dynamics 足以覆盖目标 horizon 和控制需求。"]
        if topic == "Multimodal LLMs":
            return ["默认多模态对齐质量足以支撑推理或工具调用。"]
        if topic == "Agents":
            return ["默认工具链、环境接口和反馈信号都是稳定可用的。"]
        return ["默认 abstract 中的设定能代表完整方法表现。"]

    def _build_risks(self, record: PaperRecord) -> list[str]:
        risks = []
        if not record.code_url:
            risks.append("目前更多依赖 abstract claim，短期复现价值有限。")
        if record.primary_topic == "Agents":
            risks.append("真实任务链路上的鲁棒性和成本可能比摘要看起来更敏感。")
        elif record.primary_topic == "VLA":
            risks.append("跨环境或跨 embodiment 的泛化能力仍需正文和附录验证。")
        elif record.primary_topic == "World Models":
            risks.append("长 horizon 下的误差累积风险可能被摘要低估。")
        else:
            risks.append("真实 deployment 条件和 benchmark 表现之间可能存在落差。")
        return risks[:2]

    def _build_open_questions(self, record: PaperRecord) -> list[str]:
        if record.primary_topic == "VLA":
            return ["跨 embodiment / 跨场景泛化是否仍然成立？", "失败恢复机制是 planner-guided 还是纯 policy-level？"]
        if record.primary_topic == "World Models":
            return ["世界模型和控制器的耦合是否足够稳健？", "长 horizon 预测误差如何被抑制？"]
        if record.primary_topic == "Multimodal LLMs":
            return ["真实多模态长上下文场景里的收益是否稳定？", "grounding 误差会不会拖累推理质量？"]
        if record.primary_topic == "Agents":
            return ["长任务中的 memory / verifier 成本是否可控？", "工具调用失败时的恢复策略是什么？"]
        return ["是否值得投入精读成本，需要结合正文和资源完整度继续判断。"]

    def _relation_to_prior_work(self, record: PaperRecord) -> str:
        if record.method_tags:
            return f"从摘要看，它更接近以 {record.method_tags[0]} 为核心的 {record.primary_topic} 路线。"
        return "仅靠摘要还不足以精确判断它与哪条 prior work 路线最接近。"

    def _build_domain_analysis(self, record: PaperRecord) -> dict[str, Any]:
        text = f"{record.title} {record.summary}".casefold()
        analysis: dict[str, Any] = {}
        analysis["vla"] = {
            "embodiment": self._pick(text, {"humanoid": "humanoid", "mobile": "mobile robot", "manipulation": "robot manipulation"}, default="unknown"),
            "action_space": self._pick(text, {"continuous": "continuous", "discrete": "discrete", "token": "tokenized", "chunk": "chunked"}, default="unknown"),
            "control_level": self._pick(text, {"low-level": "low-level", "mid-level": "mid-level", "high-level": "high-level", "hierarchical": "high-level"}, default="unknown"),
            "memory_usage": self._pick(text, {"episodic": "episodic memory", "summary": "summary", "history": "window", "memory": "memory"}, default="unknown"),
            "planner_usage": "yes" if "plan" in text or "planner" in text else "no",
            "reasoner_usage": "yes" if any(keyword in text for keyword in ("llm", "vlm", "reasoning")) else "no",
            "world_model_usage": "yes" if "world model" in text or "dynamics" in text else "no",
            "real_robot": "mixed" if "real robot" in text and "simulator" in text else ("yes" if "real robot" in text or "real-world" in text else "no"),
            "simulator": self._pick(text, {"simulator": "simulator", "simulation": "simulation"}, default="null"),
            "data_source": self._pick(text, {"teleop": "teleop", "internet": "internet", "simulator": "simulator", "simulation": "simulator"}, default="unknown"),
        }
        analysis["world_models"] = {
            "state_representation": self._pick(text, {"pixel": "pixel", "latent": "latent", "token": "token", "hybrid": "hybrid"}, default="unknown"),
            "prediction_target": self._pick(text, {"future frames": "future frames", "latent": "latent states", "reward": "rewards", "action": "actions"}, default="unknown"),
            "horizon": self._pick(text, {"long-horizon": "long", "short-horizon": "short", "medium": "medium"}, default="unknown"),
            "planning_interface": self._pick(text, {"mpc": "MPC", "search": "search", "sampling": "sampling", "policy": "direct policy"}, default="unknown"),
            "control_coupling": "coupled with policy / control" if any(keyword in text for keyword in ("policy", "control", "robot")) else "unclear",
        }
        analysis["multimodal_llms"] = {
            "modalities": self._modalities(text),
            "reasoning_type": self._pick(text, {"chain of thought": "cot", "cot": "cot", "tool": "tool-use", "verifier": "verifier", "self-refine": "self-refine"}, default="none"),
            "long_context_usage": "yes" if "long context" in text or "long video" in text or "million token" in text else "no",
            "grounding_method": self._pick(text, {"detection": "detection", "segmentation": "segmentation", "ocr": "OCR", "grounding": "latent grounding"}, default="none"),
        }
        analysis["agents"] = {
            "agent_type": self._pick(text, {"multi-agent": "multi-agent", "workflow": "workflow-agent", "single-agent": "single-agent"}, default="single-agent" if "agent" in text else "unknown"),
            "tooling": ", ".join(self._tools(text)) or "unknown",
            "memory_type": self._pick(text, {"long-term": "long-term", "vector": "vector", "summary": "summary", "memory": "short-term"}, default="none"),
            "planning_style": self._pick(text, {"react": "react", "hierarchical": "hierarchical", "deliberat": "deliberative", "workflow": "workflow"}, default="unknown"),
            "verification_style": self._pick(text, {"judge": "judge", "critic": "critic", "verifier": "judge"}, default="no verifier"),
        }
        return analysis

    @staticmethod
    def _pick(text: str, mapping: dict[str, str], default: str) -> str:
        for keyword, value in mapping.items():
            if keyword in text:
                return value
        return default

    @staticmethod
    def _modalities(text: str) -> list[str]:
        options = []
        for keyword, label in (
            ("image", "image"),
            ("video", "video"),
            ("text", "text"),
            ("audio", "audio"),
            ("document", "document"),
            ("robot state", "robot state"),
        ):
            if keyword in text:
                options.append(label)
        return options or ["text"]

    @staticmethod
    def _tools(text: str) -> list[str]:
        options = []
        for keyword, label in (
            ("browser", "browser"),
            ("code", "code"),
            ("retrieval", "retrieval"),
            ("api", "api"),
            ("simulator", "simulator"),
        ):
            if keyword in text:
                options.append(label)
        return options

    def _build_reproducibility(self, record: PaperRecord) -> dict[str, Any]:
        artifacts = [record.code_url, record.model_url, record.dataset_url, record.demo_url]
        artifact_count = sum(1 for item in artifacts if item)
        effort = "high"
        if artifact_count >= 3:
            effort = "low"
        elif artifact_count >= 1:
            effort = "medium"
        return {
            "code_available": bool(record.code_url),
            "weights_available": bool(record.model_url),
            "dataset_available": bool(record.dataset_url),
            "env_instructions_available": bool(record.project_url or record.demo_url),
            "repro_effort_estimate": effort,
        }

    def _build_my_take(self, record: PaperRecord) -> dict[str, str]:
        should_read = "是" if record.highlight_score >= 4.0 else ("视方向而定" if record.highlight_score >= 3.0 else "否")
        should_reproduce = "是" if record.reproducibility["code_available"] and record.highlight_score >= 3.5 else "条件满足时再看"
        borrow = ", ".join(record.method_tags[:3]) if record.method_tags else "问题定义和评测拆解方式"
        skepticism = "目前还需要正文确认 claim 的外推性。" if not record.code_url else "重点核对实验设置和资源完整度。"
        best_use_case = record.application_tags[0] if record.application_tags else record.primary_topic
        return {
            "should_i_read_it": should_read,
            "should_i_reproduce_it": should_reproduce,
            "what_can_i_borrow": borrow,
            "what_do_i_not_buy": skepticism,
            "best_use_case": best_use_case,
        }

    def _limit_records(
        self,
        records: list[PaperRecord],
        filtered_out: list[dict[str, str]],
        use_preliminary: bool = False,
    ) -> list[PaperRecord]:
        grouped = defaultdict(list)
        for record in records:
            grouped[record.primary_topic].append(record)

        selected: list[PaperRecord] = []
        for topic_name, bucket in grouped.items():
            bucket.sort(
                key=(lambda item: self._preliminary_score(item)) if use_preliminary else (lambda item: item.highlight_score),
                reverse=True,
            )
            limit = self.config.other_relevant_limit if topic_name == "Other Relevant" else self.config.selected_limit_per_topic
            selected.extend(bucket[:limit])
            for overflow in bucket[limit:]:
                filtered_out.append({"title": overflow.title, "reason": f"Trimmed by per-topic limit for {topic_name}"})
        return selected

    @staticmethod
    def _preliminary_score(record: PaperRecord) -> float:
        topic_signal = max(record.topic_scores.values(), default=0.0)
        recency_signal = 1.0 if record.published_at else 0.0
        community_signal = min(2.0, (record.hf_upvotes or 0) / 10.0)
        return round(topic_signal + recency_signal + community_signal, 2)

    def _group_by_topic(self, records: list[PaperRecord]) -> dict[str, list[PaperRecord]]:
        grouped = defaultdict(list)
        for record in records:
            grouped[record.primary_topic].append(record)
        for papers in grouped.values():
            papers.sort(key=lambda item: item.highlight_score, reverse=True)
        return dict(grouped)

    def _build_report_json(
        self,
        report_date: date,
        timezone: str,
        window_start: datetime,
        window_end: datetime,
        raw_candidates_total: int,
        deduplicated_total: int,
        selected_records: list[PaperRecord],
        highlights: list[PaperRecord],
        papers_by_topic: dict[str, list[PaperRecord]],
        highlight_ids: set[str],
        filtered_out: list[dict[str, str]],
        deduplication_log: list[str],
        crawl_errors: list[str],
        parsing_warnings: list[str],
        llm_warnings: list[str],
    ) -> dict[str, Any]:
        generated_at = datetime.now(window_end.tzinfo)
        topic_counts = self._topic_counts(selected_records)
        executive_summary = self._executive_summary(selected_records, highlights, topic_counts)
        cross_paper_insights = self._cross_paper_insights(selected_records)
        topic_overview = self._topic_overview(papers_by_topic)
        action_queue = self._action_queue(selected_records)
        non_highlight_by_topic = {
            topic: [paper.to_dict() for paper in papers if paper.paper_id not in highlight_ids]
            for topic, papers in papers_by_topic.items()
        }
        report = {
            "report_type": "daily_paper_digest",
            "report_date": report_date.isoformat(),
            "timezone": timezone,
            "generated_at": generated_at.isoformat(),
            "generator": {
                "repo_name": self.config.repo_name,
                "repo_commit": git_commit_hash(),
                "pipeline_version": self.config.pipeline_version,
            },
            "llm": {
                "enabled": self.config.llm.enabled,
                "provider": self.config.llm.provider,
                "model": self.config.llm.model or resolve_model_name(self.config.llm.model_env) or "",
                "enhanced": False,
            },
            "sources": [
                {
                    "name": "arXiv",
                    "enabled": True,
                    "query_groups": [topic.name for topic in self.config.topics],
                },
                {
                    "name": "HuggingFace Papers",
                    "enabled": True,
                    "query_groups": [topic.name for topic in self.config.topics],
                },
            ],
            "crawl_window": {
                "start": window_start.isoformat(),
                "end": window_end.isoformat(),
                "note": "日报统计窗口；不一定等同于平台原始发布时间",
            },
            "statistics": {
                "raw_candidates_total": raw_candidates_total,
                "deduplicated_total": deduplicated_total,
                "selected_total": len(selected_records),
                "highlights_total": len(highlights),
            },
            "topic_counts": topic_counts,
            "selection_policy": {
                "included_if": self.config.include_if,
                "excluded_if": self.config.exclude_if,
            },
            "ranking_policy": {
                "highlight_score_formula": self.config.ranking_formula,
                "score_range": self.config.ranking_scale,
            },
            "tags": [
                "daily-digest",
                "ai-research",
                "arxiv",
                "huggingface",
                "vla",
                "world-model",
                "mllm",
                "agents",
            ],
            "executive_summary": executive_summary,
            "metadata_summary": {
                "report_date": report_date.isoformat(),
                "timezone": timezone,
                "generated_at": generated_at.isoformat(),
                "raw_candidates_total": raw_candidates_total,
                "deduplicated_total": deduplicated_total,
                "selected_total": len(selected_records),
            },
            "query_groups": [topic.name for topic in self.config.topics],
            "query_terms": {topic.name: topic.query_terms for topic in self.config.topics},
            "topic_overview": topic_overview,
            "highlight_papers": [paper.to_dict() for paper in highlights],
            "paper_list_by_topic": non_highlight_by_topic,
            "cross_paper_insights": cross_paper_insights,
            "action_queue": action_queue,
            "appendix": {
                "raw_candidates": [
                    {"title": paper.title, "source": paper.source_primary, "topic": paper.primary_topic}
                    for paper in selected_records
                ],
                "filtered_out": filtered_out,
                "deduplication_log": deduplication_log,
                "crawl_errors": crawl_errors,
                "parsing_warnings": parsing_warnings,
                "llm_warnings": llm_warnings,
                "todo_for_tomorrow": self._todo_for_tomorrow(selected_records, filtered_out),
            },
        }
        return report

    def _maybe_llm_enhance_daily_report(self, report_json: dict[str, Any], llm_warnings: list[str]) -> None:
        summarizer = OpenAIResponsesSummarizer(self.config.llm)
        status = summarizer.status()
        if not status.available:
            if self.config.llm.enabled and status.reason:
                llm_warnings.append(status.reason)
            return
        try:
            patch = summarizer.enhance_daily_report(report_json)
        except Exception as exc:  # noqa: BLE001
            llm_warnings.append(f"LLM daily enhancement failed: {exc}")
            return

        executive = patch.get("executive_summary", {})
        if executive:
            report_json["executive_summary"]["conclusion_lines"] = executive.get(
                "conclusion_lines",
                report_json["executive_summary"]["conclusion_lines"],
            )
            report_json["executive_summary"]["research_observations"] = executive.get(
                "research_observations",
                report_json["executive_summary"]["research_observations"],
            )

        overrides = {item["paper_id"]: item for item in patch.get("paper_overrides", []) if item.get("paper_id")}
        for paper in report_json.get("highlight_papers", []):
            override = overrides.get(paper["paper_id"])
            if not override:
                continue
            paper["one_line_summary"] = override.get("one_line_summary", paper["one_line_summary"])
            paper["why_read_today"] = override.get("why_read_today", paper["why_read_today"])
            paper["strengths"] = override.get("strengths", paper["strengths"])
            paper["weaknesses"] = override.get("weaknesses", paper["weaknesses"])
            paper["open_questions"] = override.get("open_questions", paper["open_questions"])
            paper["my_take"]["what_can_i_borrow"] = override.get("what_can_i_borrow", paper["my_take"]["what_can_i_borrow"])
            paper["my_take"]["what_do_i_not_buy"] = override.get("what_do_i_not_buy", paper["my_take"]["what_do_i_not_buy"])
        for item in report_json["executive_summary"].get("top_highlights", []):
            for paper in report_json.get("highlight_papers", []):
                if paper["title"] == item["title"]:
                    item["reason"] = paper["why_read_today"]
                    break

        insights = patch.get("cross_paper_insights", {})
        if insights:
            report_json["cross_paper_insights"]["trends"] = insights.get("trends", report_json["cross_paper_insights"]["trends"])
            report_json["cross_paper_insights"]["gaps"] = insights.get("gaps", report_json["cross_paper_insights"]["gaps"])
            report_json["cross_paper_insights"]["inspiration"] = insights.get(
                "inspiration",
                report_json["cross_paper_insights"]["inspiration"],
            )
        report_json["llm"]["enhanced"] = True

    def _topic_counts(self, records: list[PaperRecord]) -> dict[str, int]:
        counts = {
            "vla": 0,
            "world_models": 0,
            "multimodal_llm": 0,
            "agents": 0,
            "other_relevant": 0,
        }
        for record in records:
            topic_id = TOPIC_NAME_TO_ID.get(record.primary_topic)
            if topic_id:
                counts[topic_id] += 1
            else:
                counts["other_relevant"] += 1
        return counts

    def _executive_summary(
        self,
        selected_records: list[PaperRecord],
        highlights: list[PaperRecord],
        topic_counts: dict[str, int],
    ) -> dict[str, Any]:
        main_topic = max(
            TOPIC_ID_TO_NAME.items(),
            key=lambda item: topic_counts.get(item[0], 0),
        )[1]
        method_counter = Counter(tag for paper in selected_records for tag in paper.method_tags)
        top_methods = [tag for tag, _ in method_counter.most_common(3)]
        read_now_count = sum(1 for paper in selected_records if paper.recommended_action == "read_now")
        observations = [
            {"label": "趋势 1", "text": f"今天出现频率最高的方法 motif 是：{top_methods[0] if top_methods else '资源和评测导向'}。"},
            {"label": "趋势 2", "text": f"最集中爆发的主题是：{main_topic}。"},
            {"label": "趋势 3", "text": f"Read-now 信号论文共有 {read_now_count} 篇。"},
            {"label": "空白点 / 机会点", "text": self._cross_paper_insights(selected_records)["gaps"][0]},
        ]
        return {
            "conclusion_lines": [
                f"今天最值得关注的方向是：`{main_topic}`",
                f"主要趋势是：`{' / '.join(top_methods) if top_methods else '资源完整度更高的条目更值得精读'}`",
                f"真正建议精读的论文数量：`{read_now_count or len(highlights)}` 篇",
            ],
            "top_highlights": [
                {"title": paper.title, "reason": paper.why_read_today}
                for paper in highlights
            ],
            "research_observations": observations,
        }

    def _topic_overview(self, papers_by_topic: dict[str, list[PaperRecord]]) -> list[dict[str, Any]]:
        overview: list[dict[str, Any]] = []
        for topic_name in [*TOPIC_ID_TO_NAME.values(), "Other Relevant"]:
            papers = papers_by_topic.get(topic_name, [])
            method_counter = Counter(tag for paper in papers for tag in paper.method_tags)
            common_tags = [tag for tag, _ in method_counter.most_common(2)] or ["暂无明显共性"]
            pitfalls = self._topic_pitfalls(topic_name, papers)
            overview.append(
                {
                    "name": topic_name,
                    "count": len(papers),
                    "judgement": self._topic_judgement(topic_name, papers, common_tags),
                    "top_papers": [paper.title for paper in papers[:3]],
                    "commonalities": common_tags,
                    "pitfalls": pitfalls,
                }
            )
        return overview

    @staticmethod
    def _topic_judgement(topic_name: str, papers: list[PaperRecord], common_tags: list[str]) -> str:
        if not papers:
            return "今天这个方向没有足够强的入选条目。"
        return f"今天 {topic_name} 方向更偏 {', '.join(common_tags)}，整体更适合做趋势跟踪而不是一次性下重注。"

    def _topic_pitfalls(self, topic_name: str, papers: list[PaperRecord]) -> list[str]:
        if not papers:
            return ["暂无足够样本。"]
        no_code_ratio = safe_percentage(sum(1 for paper in papers if not paper.code_url), len(papers))
        pitfalls = []
        if no_code_ratio > 0.5:
            pitfalls.append("多数条目暂时没有明确代码入口，复现节奏会偏慢。")
        if topic_name == "VLA" and sum(1 for paper in papers if paper.domain_analysis["vla"]["real_robot"] == "yes") == 0:
            pitfalls.append("真实机器人验证依然偏少。")
        if topic_name == "World Models":
            pitfalls.append("长 horizon 误差累积仍是核心风险。")
        if topic_name == "Agents":
            pitfalls.append("真实工具链和环境回放成本可能高于摘要给出的直觉。")
        return pitfalls[:2] or ["需要结合正文继续确认实验边界。"]

    def _cross_paper_insights(self, records: list[PaperRecord]) -> dict[str, Any]:
        method_counter = Counter(tag for paper in records for tag in paper.method_tags)
        trends = [
            f"{tag} 在今天的入选论文里重复出现 {count} 次。"
            for tag, count in method_counter.most_common(3)
        ] or ["今天的样本量还不足以形成稳定趋势。"]
        motifs = {}
        for motif in ("memory", "planning", "retrieval", "verification", "world model"):
            count = sum(1 for paper in records if any(motif in tag.casefold() for tag in paper.method_tags))
            motifs[motif] = f"今天出现 {count} 次，主要集中在 {self._top_topics_for_motif(records, motif)}。"
        gaps = self._research_gaps(records)
        inspiration = self._research_inspiration(records)
        return {
            "trends": trends,
            "motifs": motifs,
            "gaps": gaps,
            "inspiration": inspiration,
        }

    @staticmethod
    def _top_topics_for_motif(records: list[PaperRecord], motif: str) -> str:
        counter = Counter(
            paper.primary_topic
            for paper in records
            if any(motif in tag.casefold() for tag in paper.method_tags)
        )
        return ", ".join(topic for topic, _ in counter.most_common(2)) or "暂无明显集中方向"

    def _research_gaps(self, records: list[PaperRecord]) -> list[str]:
        gaps = []
        if sum(1 for paper in records if paper.primary_topic == "VLA" and paper.domain_analysis["vla"]["real_robot"] == "yes") == 0:
            gaps.append("真实机器人验证仍然稀缺，尤其缺少能跨 embodiment 的证据。")
        if sum(1 for paper in records if paper.reproducibility["code_available"]) < max(1, len(records) // 3):
            gaps.append("可直接复现的开源资源占比仍偏低。")
        if sum(1 for paper in records if paper.primary_topic == "Agents" and "verification" in paper.method_tags) == 0:
            gaps.append("agent 方向里 verifier / judge 设计还没有形成明显主线。")
        return gaps[:3] or ["今天的样本里暂时没有特别鲜明的结构性缺口。"]

    def _research_inspiration(self, records: list[PaperRecord]) -> list[str]:
        method_counter = Counter(tag for paper in records for tag in paper.method_tags)
        inspirations = [
            f"可以优先整理 {tag} 相关论文，做成一页 related work matrix。"
            for tag, _ in method_counter.most_common(3)
        ]
        return inspirations or ["先积累 3-5 天数据，再做横向趋势判断会更稳。"]

    def _action_queue(self, records: list[PaperRecord]) -> dict[str, Any]:
        queue = {"read_now": [], "track": [], "reproduce": [], "ignore": []}
        for record in records:
            item = {"title": record.title, "reason": record.why_read_today}
            if record.recommended_action in ("read_now", "track", "reproduce"):
                queue[record.recommended_action].append(item)
            else:
                queue["ignore"].append({"title": record.title, "reason": "Current score is below the action threshold."})
        return queue

    def _todo_for_tomorrow(self, records: list[PaperRecord], filtered_out: list[dict[str, str]]) -> list[str]:
        todos = []
        for record in records[:3]:
            if not record.code_url:
                todos.append(f"回看 {record.title} 是否补出了 code / project link。")
        if filtered_out:
            todos.append("检查被 classifier 或窗口规则过滤掉的边界样本，必要时扩充关键词。")
        return todos[:3] or ["继续观察趋势是否稳定。"]
