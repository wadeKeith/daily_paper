from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

import httpx

from daily_paper.models import CandidatePaper, TopicProfile
from daily_paper.utils import extract_arxiv_id, normalize_whitespace, parse_iso_datetime


ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class ArxivClient:
    def __init__(self, user_agent: str, polite_delay_seconds: float = 3.2) -> None:
        self.client = httpx.Client(
            base_url="https://export.arxiv.org",
            headers={"User-Agent": user_agent},
            timeout=30.0,
            follow_redirects=True,
        )
        self.polite_delay_seconds = polite_delay_seconds
        self._last_request_at = 0.0

    def close(self) -> None:
        self.client.close()

    def search_topic(self, topic: TopicProfile, max_results: int) -> list[CandidatePaper]:
        self._maybe_wait()
        response = self.client.get(
            "/api/query",
            params={
                "search_query": self._build_query(topic.query_terms),
                "start": 0,
                "max_results": max_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            },
        )
        response.raise_for_status()
        self._last_request_at = time.monotonic()
        return self._parse_feed(response.text, topic.name)

    def _maybe_wait(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.polite_delay_seconds:
            time.sleep(self.polite_delay_seconds - elapsed)

    @staticmethod
    def _build_query(terms: list[str]) -> str:
        parts = []
        for term in terms:
            if any(char in term for char in (' ', '-', '/')):
                parts.append(f'all:"{term}"')
            else:
                parts.append(f"all:{term}")
        return " OR ".join(parts)

    def _parse_feed(self, xml_text: str, query_group: str) -> list[CandidatePaper]:
        root = ET.fromstring(xml_text)
        items: list[CandidatePaper] = []
        for entry in root.findall("atom:entry", ATOM_NS):
            identifier = entry.findtext("atom:id", default="", namespaces=ATOM_NS)
            arxiv_id, version = extract_arxiv_id(identifier)
            title = normalize_whitespace(entry.findtext("atom:title", default="", namespaces=ATOM_NS))
            summary = normalize_whitespace(entry.findtext("atom:summary", default="", namespaces=ATOM_NS))
            authors = [
                normalize_whitespace(author.findtext("atom:name", default="", namespaces=ATOM_NS))
                for author in entry.findall("atom:author", ATOM_NS)
            ]
            categories = [item.attrib.get("term", "") for item in entry.findall("atom:category", ATOM_NS)]
            pdf_url = None
            for link in entry.findall("atom:link", ATOM_NS):
                href = link.attrib.get("href")
                if link.attrib.get("title") == "pdf" and href:
                    pdf_url = href.replace("http://", "https://")
                    break
            primary_category = entry.find("arxiv:primary_category", ATOM_NS)
            items.append(
                CandidatePaper(
                    title=title,
                    authors=[author for author in authors if author],
                    summary=summary,
                    source_name="arXiv",
                    source_alias=f"arXiv / {query_group}",
                    source_aliases=[f"arXiv / {query_group}"],
                    paper_url=identifier.replace("http://", "https://"),
                    pdf_url=pdf_url,
                    arxiv_id=arxiv_id,
                    version=version,
                    published_at=parse_iso_datetime(entry.findtext("atom:published", namespaces=ATOM_NS)),
                    updated_at=parse_iso_datetime(entry.findtext("atom:updated", namespaces=ATOM_NS)),
                    primary_category=primary_category.attrib.get("term") if primary_category is not None else None,
                    categories=[category for category in categories if category],
                    comment=normalize_whitespace(entry.findtext("arxiv:comment", default="", namespaces=ATOM_NS)) or None,
                    journal_ref=normalize_whitespace(entry.findtext("arxiv:journal_ref", default="", namespaces=ATOM_NS)) or None,
                    doi=normalize_whitespace(entry.findtext("arxiv:doi", default="", namespaces=ATOM_NS)) or None,
                    query_groups=[query_group],
                    raw_source_metadata={"query": query_group},
                )
            )
        return items
