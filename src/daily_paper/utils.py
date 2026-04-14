from __future__ import annotations

import math
import re
import subprocess
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo


ARXIV_ID_RE = re.compile(r"(?P<id>\d{4}\.\d{4,5})(?P<version>v\d+)?$")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def normalize_whitespace(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def normalize_title(title: str) -> str:
    return normalize_whitespace(title).casefold()


def slugify(value: str) -> str:
    value = normalize_title(value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "paper"


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    candidate = value.replace("Z", "+00:00")
    return datetime.fromisoformat(candidate)


def ensure_timezone(value: datetime, timezone: str) -> datetime:
    tz = ZoneInfo(timezone)
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def report_window(report_date: date, timezone: str, lookback_days: int) -> tuple[datetime, datetime]:
    tz = ZoneInfo(timezone)
    start_day = report_date - timedelta(days=lookback_days)
    start = datetime.combine(start_day, time.min, tzinfo=tz)
    end = datetime.combine(report_date, time(hour=23, minute=59, second=59), tzinfo=tz)
    return start, end


def within_window(value: datetime | None, start: datetime, end: datetime) -> bool:
    if value is None:
        return False
    candidate = value.astimezone(start.tzinfo)
    return start <= candidate <= end


def split_sentences(text: str, limit: int | None = None) -> list[str]:
    normalized = normalize_whitespace(text)
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+", normalized)
    parts = [part.strip() for part in parts if part.strip()]
    return parts[:limit] if limit else parts


def first_non_empty(values: Iterable[str | None], fallback: str = "") -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return fallback


def extract_arxiv_id(identifier: str | None) -> tuple[str | None, str | None]:
    if not identifier:
        return None, None
    normalized = identifier.rstrip("/").split("/")[-1]
    match = ARXIV_ID_RE.search(normalized)
    if not match:
        return None, None
    return match.group("id"), match.group("version")


def clip_text(text: str, limit: int) -> str:
    normalized = normalize_whitespace(text)
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def safe_percentage(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def log_score(value: int | None) -> float:
    if not value or value <= 0:
        return 1.0
    return min(5.0, 1.0 + math.log2(value + 1))


def git_commit_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            cwd=repo_root(),
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
