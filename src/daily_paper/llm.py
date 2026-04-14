from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from daily_paper.env import load_env_file, resolve_api_keys, resolve_base_url, resolve_model_name
from daily_paper.models import LLMConfig
from daily_paper.utils import clip_text


DAILY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "executive_summary": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "conclusion_lines": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
                "research_observations": {
                    "type": "array",
                    "minItems": 4,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "label": {"type": "string"},
                            "text": {"type": "string"},
                        },
                        "required": ["label", "text"],
                    },
                },
            },
            "required": ["conclusion_lines", "research_observations"],
        },
        "paper_overrides": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "paper_id": {"type": "string"},
                    "one_line_summary": {"type": "string"},
                    "why_read_today": {"type": "string"},
                    "strengths": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
                    "weaknesses": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
                    "open_questions": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
                    "what_can_i_borrow": {"type": "string"},
                    "what_do_i_not_buy": {"type": "string"},
                },
                "required": [
                    "paper_id",
                    "one_line_summary",
                    "why_read_today",
                    "strengths",
                    "weaknesses",
                    "open_questions",
                    "what_can_i_borrow",
                    "what_do_i_not_buy",
                ],
            },
        },
        "cross_paper_insights": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "trends": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
                "gaps": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
                "inspiration": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
            },
            "required": ["trends", "gaps", "inspiration"],
        },
    },
    "required": ["executive_summary", "paper_overrides", "cross_paper_insights"],
}

AGGREGATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "headline": {"type": "string"},
        "summary_points": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 4},
        "trends": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 4},
        "gaps": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 4},
        "next_actions": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 4},
    },
    "required": ["headline", "summary_points", "trends", "gaps", "next_actions"],
}


@dataclass(slots=True)
class SummarizerStatus:
    available: bool
    reason: str | None = None


class OpenAIResponsesSummarizer:
    def __init__(self, config: LLMConfig) -> None:
        load_env_file()
        self.config = config
        self.api_keys = resolve_api_keys(config.api_key_env)
        self.model = config.model or resolve_model_name(config.model_env)
        self.base_url = resolve_base_url(config.api_base)

    def status(self) -> SummarizerStatus:
        if not self.config.enabled:
            return SummarizerStatus(False, "LLM summarizer disabled in config")
        if self.config.provider not in {"openai_responses", "openai_chat_completions"}:
            return SummarizerStatus(False, f"Unsupported LLM provider: {self.config.provider}")
        if not self.api_keys:
            return SummarizerStatus(False, f"Missing API key env: {self.config.api_key_env}")
        if not self.model:
            missing = self.config.model_env or "model"
            return SummarizerStatus(False, f"Missing model config or env: {missing}")
        return SummarizerStatus(True)

    def enhance_daily_report(self, report_json: dict[str, Any]) -> dict[str, Any]:
        highlights = report_json.get("highlight_papers", [])[: self.config.max_daily_highlights]
        payload = {
            "report_date": report_json.get("report_date"),
            "topic_counts": report_json.get("topic_counts"),
            "top_highlights": [self._daily_paper_payload(item) for item in highlights],
            "cross_paper_insights": report_json.get("cross_paper_insights"),
        }
        prompt = (
            "你是一个严谨的 AI 研究日报编辑。请基于给定 JSON，为 VLA、世界模型、多模态大模型、智能体日报做增强。"
            "要求：全部使用简洁中文；不要空话；保留研究判断；只输出符合 schema 的 JSON；"
            "conclusion_lines 固定 3 条；research_observations 固定 4 条，标签分别写成"
            "“趋势 1”“趋势 2”“趋势 3”“空白点 / 机会点”；"
            "paper_overrides 只覆盖输入里的 paper_id。"
            "\n\nINPUT_JSON:\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )
        return self._request_json(
            schema_name="daily_digest_enhancement",
            schema=DAILY_SCHEMA,
            prompt=prompt,
        )

    def summarize_period_report(self, report_json: dict[str, Any]) -> dict[str, Any]:
        top_papers = report_json.get("top_papers", [])[: self.config.max_aggregate_papers]
        payload = {
            "report_type": report_json.get("report_type"),
            "period_label": report_json.get("period_label"),
            "date_range": report_json.get("date_range"),
            "statistics": report_json.get("statistics"),
            "topic_counts": report_json.get("topic_counts"),
            "method_tag_counts": report_json.get("method_tag_counts"),
            "top_papers": [
                {
                    "paper_id": paper.get("paper_id"),
                    "title": paper.get("title"),
                    "primary_topic": paper.get("primary_topic"),
                    "mention_count": paper.get("mention_count"),
                    "highlight_count": paper.get("highlight_count"),
                    "best_score": paper.get("best_score"),
                    "method_tags": paper.get("method_tags"),
                    "application_tags": paper.get("application_tags"),
                }
                for paper in top_papers
            ],
        }
        prompt = (
            "你是一个严谨的 AI 研究周报/月报编辑。请基于给定 JSON 生成高密度中文总结。"
            "要求：只输出符合 schema 的 JSON；headline 用一句话点出这段周期最重要的研究变化；"
            "summary_points / trends / gaps / next_actions 各写 3~4 条，避免空泛结论。"
            "\n\nINPUT_JSON:\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )
        return self._request_json(
            schema_name="period_digest_summary",
            schema=AGGREGATE_SCHEMA,
            prompt=prompt,
        )

    def _request_json(self, schema_name: str, schema: dict[str, Any], prompt: str) -> dict[str, Any]:
        status = self.status()
        if not status.available:
            raise RuntimeError(status.reason or "LLM summarizer unavailable")
        if self._use_chat_completions():
            return self._request_json_chat_completions(prompt)
        return self._request_json_responses(schema_name, schema, prompt)

    def _request_json_responses(self, schema_name: str, schema: dict[str, Any], prompt: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for api_key in self.api_keys:
            try:
                with httpx.Client(
                    base_url=self.base_url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    timeout=float(self.config.timeout_seconds),
                ) as client:
                    payload = {
                        "model": self.model,
                        "input": prompt,
                        "text": {
                            "format": {
                                "type": "json_schema",
                                "name": schema_name,
                                "schema": schema,
                                "strict": True,
                            }
                        },
                    }
                    if self.config.reasoning_effort:
                        payload["reasoning"] = {"effort": self.config.reasoning_effort}
                    response = client.post("/responses", json=payload)
                    response.raise_for_status()
                    return self._extract_json(response.json())
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        raise RuntimeError(f"All LLM API keys failed for Responses API: {last_error}")

    def _request_json_chat_completions(self, prompt: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for api_key in self.api_keys:
            try:
                with httpx.Client(
                    timeout=float(self.config.timeout_seconds),
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                ) as client:
                    payload = {
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a rigorous AI research editor. Return only valid JSON matching the user request. Do not wrap JSON in markdown.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.2,
                    }
                    response = client.post(self.base_url, json=payload)
                    response.raise_for_status()
                    return self._extract_chat_completions_json(response.json())
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        raise RuntimeError(f"All LLM API keys failed for Chat Completions API: {last_error}")

    def _use_chat_completions(self) -> bool:
        if self.config.provider == "openai_chat_completions":
            return True
        return self.base_url.endswith("/chat/completions")

    def _extract_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
            return json.loads(payload["output_text"])
        for item in payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    text = content["text"]
                    if isinstance(text, dict):
                        text = text.get("value")
                    if text:
                        return json.loads(text)
        raise ValueError("Could not extract JSON from Responses API payload")

    def _extract_chat_completions_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        choices = payload.get("choices", [])
        if not choices:
            raise ValueError("No choices found in chat completions payload")
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return json.loads(content)
        if isinstance(content, list):
            fragments = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") in {"text", "output_text"} and item.get("text"):
                        text = item["text"]
                        if isinstance(text, dict):
                            text = text.get("value")
                        if text:
                            fragments.append(text)
            if fragments:
                return json.loads("".join(fragments))
        raise ValueError("Could not extract JSON from chat completions payload")

    @staticmethod
    def _daily_paper_payload(paper: dict[str, Any]) -> dict[str, Any]:
        return {
            "paper_id": paper.get("paper_id"),
            "title": paper.get("title"),
            "primary_topic": paper.get("primary_topic"),
            "summary": clip_text(paper.get("summary", ""), 1000),
            "one_line_summary": paper.get("one_line_summary"),
            "method_tags": paper.get("method_tags", []),
            "application_tags": paper.get("application_tags", []),
            "highlight_score": paper.get("highlight_score"),
            "recommended_action": paper.get("recommended_action"),
            "resource_links": {
                "code": bool(paper.get("code_url")),
                "project": bool(paper.get("project_url")),
                "model": bool(paper.get("model_url")),
                "dataset": bool(paper.get("dataset_url")),
                "demo": bool(paper.get("demo_url")),
            },
        }
