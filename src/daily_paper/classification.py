from __future__ import annotations

from dataclasses import dataclass

from daily_paper.models import PipelineConfig, TopicProfile
from daily_paper.utils import normalize_whitespace


@dataclass(slots=True)
class ClassificationResult:
    topic_scores: dict[str, float]
    matched_topics: list[str]
    primary_topic: str
    method_tags: list[str]
    application_tags: list[str]
    include: bool


class TopicClassifier:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def classify(self, title: str, summary: str, query_groups: list[str]) -> ClassificationResult:
        text = normalize_whitespace(f"{title} {summary}").casefold()
        topic_scores: dict[str, float] = {}
        method_tags: set[str] = set()
        application_tags: set[str] = set()
        normalized_groups = {group.casefold() for group in query_groups}

        for topic in self.config.topics:
            score = self._score_topic(text, topic, normalized_groups)
            topic_scores[topic.summary_name] = score
            if score > 0:
                method_tags.update(self._collect_tags(text, topic.method_tags))
                application_tags.update(self._collect_tags(text, topic.application_tags))

        primary_topic, primary_score = max(topic_scores.items(), key=lambda item: item[1])
        matched_topics = [
            name
            for name, score in sorted(topic_scores.items(), key=lambda item: item[1], reverse=True)
            if score >= max(2.2, primary_score - 0.75)
        ]
        related_score = self._score_related(text)
        include = primary_score >= 2.2 or related_score >= 1.7
        if not include:
            matched_topics = []
            primary_topic = "Other Relevant"
        elif primary_score < 2.2:
            primary_topic = "Other Relevant"
            matched_topics = ["Other Relevant"]
        return ClassificationResult(
            topic_scores=topic_scores,
            matched_topics=matched_topics or ["Other Relevant"],
            primary_topic=primary_topic,
            method_tags=sorted(method_tags),
            application_tags=sorted(application_tags),
            include=include,
        )

    def _score_topic(self, text: str, topic: TopicProfile, query_groups: set[str]) -> float:
        score = 0.0
        if topic.name.casefold() in query_groups or topic.summary_name.casefold() in query_groups:
            score += 0.6
        for keyword in topic.high_keywords:
            if self._contains(text, keyword):
                score += self._keyword_weight(keyword, base=1.2)
        for keyword in topic.medium_keywords:
            if self._contains(text, keyword):
                score += self._keyword_weight(keyword, base=0.6)
        return min(5.0, round(score, 2))

    def _score_related(self, text: str) -> float:
        score = 0.0
        for keyword in self.config.related_keywords:
            if self._contains(text, keyword):
                score += self._keyword_weight(keyword, base=0.7)
        return min(5.0, round(score, 2))

    @staticmethod
    def _collect_tags(text: str, tag_map: dict[str, list[str]]) -> list[str]:
        matches = []
        for tag, keywords in tag_map.items():
            if any(TopicClassifier._contains(text, keyword) for keyword in keywords):
                matches.append(tag)
        return matches

    @staticmethod
    def _contains(text: str, keyword: str) -> bool:
        return normalize_whitespace(keyword).casefold() in text

    @staticmethod
    def _keyword_weight(keyword: str, base: float) -> float:
        normalized = normalize_whitespace(keyword)
        multiplier = 1.2 if (" " in normalized or "-" in normalized) else 0.75
        return round(base * multiplier, 2)

