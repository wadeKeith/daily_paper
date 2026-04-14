from __future__ import annotations

from datetime import date

import httpx

from daily_paper.models import CandidatePaper
from daily_paper.utils import normalize_whitespace, parse_iso_datetime


class HuggingFacePapersClient:
    def __init__(self, user_agent: str) -> None:
        self.client = httpx.Client(
            base_url="https://huggingface.co",
            headers={"User-Agent": user_agent},
            timeout=30.0,
            follow_redirects=True,
        )

    def close(self) -> None:
        self.client.close()

    def list_recent_papers(self, limit: int) -> list[CandidatePaper]:
        response = self.client.get("/api/papers", params={"limit": min(limit, 100)})
        response.raise_for_status()
        payload = response.json()
        return [self._candidate_from_paper(item, alias="HuggingFace Papers / Recent") for item in payload]

    def list_daily_papers(self, target_date: date, limit: int) -> list[CandidatePaper]:
        response = self.client.get(
            "/api/daily_papers",
            params={"date": target_date.isoformat(), "limit": limit},
        )
        response.raise_for_status()
        payload = response.json()
        items: list[CandidatePaper] = []
        for item in payload:
            paper_payload = item.get("paper", item)
            candidate = self._candidate_from_paper(paper_payload, alias="HuggingFace Papers / Daily Papers")
            candidate.submitted_on_daily_at = parse_iso_datetime(paper_payload.get("submittedOnDailyAt") or item.get("submittedOnDailyAt"))
            candidate.raw_source_metadata["daily_published_at"] = item.get("publishedAt")
            items.append(candidate)
        return items

    def get_paper_detail(self, arxiv_id: str) -> dict | None:
        response = self.client.get(f"/api/papers/{arxiv_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def get_linked_repos(self, arxiv_id: str) -> dict | None:
        response = self.client.get(f"/api/arxiv/{arxiv_id}/repos")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def _candidate_from_paper(self, payload: dict, alias: str) -> CandidatePaper:
        authors = [normalize_whitespace(author.get("name", "")) for author in payload.get("authors", [])]
        arxiv_id = payload.get("id")
        paper_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else payload.get("url", "https://huggingface.co/papers")
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else None
        return CandidatePaper(
            title=normalize_whitespace(payload.get("title", "")),
            authors=[author for author in authors if author],
            summary=normalize_whitespace(payload.get("summary", "")),
            source_name="HuggingFace Papers",
            source_alias=alias,
            source_aliases=[alias],
            paper_url=paper_url,
            pdf_url=pdf_url,
            hf_paper_url=f"https://huggingface.co/papers/{arxiv_id}" if arxiv_id else None,
            arxiv_id=arxiv_id,
            version=None,
            published_at=parse_iso_datetime(payload.get("publishedAt")),
            updated_at=parse_iso_datetime(payload.get("updatedAt") or payload.get("publishedAt")),
            code_url=payload.get("githubRepo"),
            project_url=payload.get("projectPage"),
            hf_upvotes=payload.get("upvotes"),
            hf_ai_summary=normalize_whitespace(payload.get("ai_summary", "")) or None,
            hf_ai_keywords=[normalize_whitespace(item) for item in payload.get("ai_keywords", []) if normalize_whitespace(item)],
            submitted_on_daily_at=parse_iso_datetime(payload.get("submittedOnDailyAt")),
            raw_source_metadata={"alias": alias},
        )
