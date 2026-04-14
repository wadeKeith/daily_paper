from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from daily_paper.env import resolve_model_name
from daily_paper.llm import OpenAIResponsesSummarizer
from daily_paper.models import PipelineConfig
from daily_paper.render import render_markdown
from daily_paper.utils import git_commit_hash


@dataclass(slots=True)
class PeriodWindow:
    period_type: str
    period_label: str
    start_date: date
    end_date: date


class AggregatePipeline:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def aggregate_weekly(self, anchor_date: date, input_dir: str | Path) -> dict[str, Any]:
        iso_year, iso_week, iso_weekday = anchor_date.isocalendar()
        start_date = anchor_date - timedelta(days=iso_weekday - 1)
        end_date = start_date + timedelta(days=6)
        window = PeriodWindow(
            period_type="weekly",
            period_label=f"{iso_year}-W{iso_week:02d}",
            start_date=start_date,
            end_date=end_date,
        )
        return self._aggregate(window, input_dir, top_paper_limit=self.config.aggregation["weekly_top_papers"])

    def aggregate_monthly(self, anchor_date: date, input_dir: str | Path) -> dict[str, Any]:
        start_date = anchor_date.replace(day=1)
        if anchor_date.month == 12:
            end_date = anchor_date.replace(year=anchor_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = anchor_date.replace(month=anchor_date.month + 1, day=1) - timedelta(days=1)
        window = PeriodWindow(
            period_type="monthly",
            period_label=f"{anchor_date.year}-{anchor_date.month:02d}",
            start_date=start_date,
            end_date=end_date,
        )
        return self._aggregate(window, input_dir, top_paper_limit=self.config.aggregation["monthly_top_papers"])

    def _aggregate(self, window: PeriodWindow, input_dir: str | Path, top_paper_limit: int) -> dict[str, Any]:
        reports = self._load_reports(input_dir, window.start_date, window.end_date)
        if not reports:
            raise ValueError(f"No daily JSON reports found for {window.period_label} in {input_dir}")

        top_days_limit = self.config.aggregation["top_days_limit"]
        top_tags_limit = self.config.aggregation["top_tags_limit"]
        period_stats = self._period_statistics(reports)
        top_papers = self._top_papers(reports, limit=top_paper_limit)
        top_days = self._top_days(reports, limit=top_days_limit)
        method_tag_counts = Counter()
        application_tag_counts = Counter()
        topic_counts = Counter()
        for report in reports:
            counts = report.get("topic_counts", {})
            topic_counts.update(
                {
                    "VLA": counts.get("vla", 0),
                    "World Models": counts.get("world_models", 0),
                    "Multimodal LLMs": counts.get("multimodal_llm", 0),
                    "Agents": counts.get("agents", 0),
                    "Other Relevant": counts.get("other_relevant", 0),
                }
            )
            for paper in report.get("highlight_papers", []):
                method_tag_counts.update(paper.get("method_tags", []))
                application_tag_counts.update(paper.get("application_tags", []))
            for bucket in report.get("paper_list_by_topic", {}).values():
                for paper in bucket:
                    method_tag_counts.update(paper.get("method_tags", []))
                    application_tag_counts.update(paper.get("application_tags", []))

        report_json = {
            "report_type": f"{window.period_type}_paper_digest",
            "period_type": window.period_type,
            "period_label": window.period_label,
            "date_range": {
                "start": window.start_date.isoformat(),
                "end": window.end_date.isoformat(),
            },
            "generated_at": datetime.now(ZoneInfo(self.config.timezone)).isoformat(),
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
            "statistics": period_stats,
            "topic_counts": dict(topic_counts),
            "top_papers": top_papers,
            "top_days": top_days,
            "method_tag_counts": method_tag_counts.most_common(top_tags_limit),
            "application_tag_counts": application_tag_counts.most_common(top_tags_limit),
            "daily_reports": [
                {
                    "report_date": report["report_date"],
                    "selected_total": report["statistics"]["selected_total"],
                    "highlights_total": report["statistics"]["highlights_total"],
                    "top_topic": self._top_topic_name(report.get("topic_counts", {})),
                }
                for report in reports
            ],
            "executive_summary": self._deterministic_period_summary(window, period_stats, topic_counts, top_papers),
            "trend_analysis": self._deterministic_trend_analysis(method_tag_counts, application_tag_counts, top_papers, topic_counts),
            "appendix": {
                "source_reports": [report["report_date"] for report in reports],
                "llm_warnings": [],
            },
        }
        self._maybe_llm_enhance_period_report(report_json)
        markdown = render_markdown(report_json, template_name="period_report_template.md")
        return {"markdown": markdown, "json": report_json}

    def _load_reports(self, input_dir: str | Path, start_date: date, end_date: date) -> list[dict[str, Any]]:
        base = Path(input_dir)
        reports = []
        current = start_date
        while current <= end_date:
            candidate = base / f"{current.isoformat()}.json"
            if candidate.exists():
                reports.append(json.loads(candidate.read_text(encoding="utf-8")))
            current += timedelta(days=1)
        reports.sort(key=lambda item: item["report_date"])
        return reports

    def _period_statistics(self, reports: list[dict[str, Any]]) -> dict[str, int]:
        unique_papers = set()
        unique_highlights = set()
        total_mentions = 0
        total_highlights = 0
        for report in reports:
            total_mentions += report["statistics"]["selected_total"]
            total_highlights += report["statistics"]["highlights_total"]
            for paper in report.get("highlight_papers", []):
                unique_papers.add(paper["paper_id"])
                unique_highlights.add(paper["paper_id"])
            for bucket in report.get("paper_list_by_topic", {}).values():
                for paper in bucket:
                    unique_papers.add(paper["paper_id"])
        return {
            "reports_included": len(reports),
            "papers_mentioned_total": total_mentions,
            "unique_papers_total": len(unique_papers),
            "highlight_mentions_total": total_highlights,
            "unique_highlights_total": len(unique_highlights),
        }

    def _top_papers(self, reports: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        bucket: dict[str, dict[str, Any]] = {}
        for report in reports:
            report_date = report["report_date"]
            combined = list(report.get("highlight_papers", []))
            for papers in report.get("paper_list_by_topic", {}).values():
                combined.extend(papers)
            for paper in combined:
                entry = bucket.setdefault(
                    paper["paper_id"],
                    {
                        "paper_id": paper["paper_id"],
                        "title": paper["title"],
                        "primary_topic": paper.get("primary_topic"),
                        "method_tags": paper.get("method_tags", []),
                        "application_tags": paper.get("application_tags", []),
                        "mention_count": 0,
                        "highlight_count": 0,
                        "read_now_count": 0,
                        "reproduce_count": 0,
                        "best_score": 0.0,
                        "score_total": 0.0,
                        "source_primary": paper.get("source_primary"),
                        "paper_url": paper.get("paper_url"),
                        "code_url": paper.get("code_url"),
                        "first_seen_report_date": report_date,
                        "last_seen_report_date": report_date,
                    },
                )
                entry["mention_count"] += 1
                entry["highlight_count"] += 1 if paper in report.get("highlight_papers", []) else 0
                entry["read_now_count"] += 1 if paper.get("recommended_action") == "read_now" else 0
                entry["reproduce_count"] += 1 if paper.get("recommended_action") == "reproduce" else 0
                entry["best_score"] = max(entry["best_score"], paper.get("highlight_score", 0.0))
                entry["score_total"] += paper.get("highlight_score", 0.0)
                entry["last_seen_report_date"] = report_date
        top = []
        for item in bucket.values():
            item["avg_score"] = round(item["score_total"] / max(item["mention_count"], 1), 2)
            item.pop("score_total", None)
            top.append(item)
        top.sort(
            key=lambda item: (
                item["highlight_count"],
                item["read_now_count"],
                item["mention_count"],
                item["best_score"],
            ),
            reverse=True,
        )
        return top[:limit]

    def _top_days(self, reports: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        rows = [
            {
                "report_date": report["report_date"],
                "selected_total": report["statistics"]["selected_total"],
                "highlights_total": report["statistics"]["highlights_total"],
                "top_topic": self._top_topic_name(report.get("topic_counts", {})),
            }
            for report in reports
        ]
        rows.sort(key=lambda item: (item["selected_total"], item["highlights_total"]), reverse=True)
        return rows[:limit]

    @staticmethod
    def _top_topic_name(topic_counts: dict[str, int]) -> str:
        mapping = {
            "vla": "VLA",
            "world_models": "World Models",
            "multimodal_llm": "Multimodal LLMs",
            "agents": "Agents",
            "other_relevant": "Other Relevant",
        }
        if not topic_counts:
            return "Unknown"
        key = max(topic_counts.items(), key=lambda item: item[1])[0]
        return mapping.get(key, key)

    def _deterministic_period_summary(
        self,
        window: PeriodWindow,
        stats: dict[str, int],
        topic_counts: Counter[str],
        top_papers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        dominant_topic = topic_counts.most_common(1)[0][0] if topic_counts else "Unknown"
        top_titles = ", ".join(paper["title"] for paper in top_papers[:3]) if top_papers else "暂无"
        headline = (
            f"{window.period_label} 期间最活跃的主题是 {dominant_topic}，"
            f"共覆盖 {stats['unique_papers_total']} 篇独立论文。"
        )
        summary_points = [
            f"周期内共纳入 {stats['reports_included']} 份日报，累计提及 {stats['papers_mentioned_total']} 篇论文记录。",
            f"高亮论文累计出现 {stats['highlight_mentions_total']} 次，其中独立高亮论文 {stats['unique_highlights_total']} 篇。",
            f"本周期最值得回看的一组论文包括：{top_titles}。",
        ]
        return {"headline": headline, "summary_points": summary_points}

    def _deterministic_trend_analysis(
        self,
        method_tag_counts: Counter[str],
        application_tag_counts: Counter[str],
        top_papers: list[dict[str, Any]],
        topic_counts: Counter[str],
    ) -> dict[str, Any]:
        top_method_tags = [tag for tag, _ in method_tag_counts.most_common(3)] or ["暂无稳定 method motif"]
        top_app_tags = [tag for tag, _ in application_tag_counts.most_common(3)] or ["暂无稳定 application motif"]
        trends = [
            f"重复出现最多的方法标签是：{', '.join(top_method_tags)}。",
            f"主要落地方向集中在：{', '.join(top_app_tags)}。",
            f"主导主题是：{topic_counts.most_common(1)[0][0] if topic_counts else 'Unknown'}。",
        ]
        gaps = [
            "仍需继续观察哪些高频论文真正有可复现资源。",
            "跨主题的方法迁移价值还需要更长时间窗才能看清。",
            "高亮论文之外的长尾样本仍值得人工抽查，避免错过边界创新。",
        ]
        next_actions = [
            f"优先精读 {paper['title']}。" for paper in top_papers[:3]
        ] or ["继续累计日报数据。"]
        return {"trends": trends, "gaps": gaps, "next_actions": next_actions}

    def _maybe_llm_enhance_period_report(self, report_json: dict[str, Any]) -> None:
        summarizer = OpenAIResponsesSummarizer(self.config.llm)
        status = summarizer.status()
        if not status.available:
            if self.config.llm.enabled and status.reason:
                report_json["appendix"]["llm_warnings"].append(status.reason)
            return
        try:
            patch = summarizer.summarize_period_report(report_json)
        except Exception as exc:  # noqa: BLE001
            report_json["appendix"]["llm_warnings"].append(f"LLM period enhancement failed: {exc}")
            return

        report_json["executive_summary"]["headline"] = patch.get("headline", report_json["executive_summary"]["headline"])
        report_json["executive_summary"]["summary_points"] = patch.get(
            "summary_points",
            report_json["executive_summary"]["summary_points"],
        )
        report_json["trend_analysis"]["trends"] = patch.get("trends", report_json["trend_analysis"]["trends"])
        report_json["trend_analysis"]["gaps"] = patch.get("gaps", report_json["trend_analysis"]["gaps"])
        report_json["trend_analysis"]["next_actions"] = patch.get(
            "next_actions",
            report_json["trend_analysis"]["next_actions"],
        )
        report_json["llm"]["enhanced"] = True
