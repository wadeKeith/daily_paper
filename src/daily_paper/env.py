from __future__ import annotations

import os
import shlex
from pathlib import Path

from daily_paper.utils import repo_root


def default_env_path() -> Path:
    return repo_root() / ".env"


def load_env_file(path: str | Path | None = None, override: bool = False) -> dict[str, str]:
    env_path = Path(path) if path else default_env_path()
    if not env_path.exists():
        return {}

    loaded: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        parsed = _parse_value(value)
        loaded[key] = parsed
        if override or key not in os.environ:
            os.environ[key] = parsed
    return loaded


def resolve_model_name(preferred_env: str | None = None) -> str | None:
    candidates = []
    if preferred_env:
        candidates.append(preferred_env)
    candidates.extend(
        [
            "DAILY_PAPER_LLM_MODEL",
            "IDEA_MODEL",
            "EXP_MODEL",
            "IDEA_AGENT_MODEL",
            "IDEA_CRITIC_MODEL",
            "IDEA_STOP_MODEL",
        ]
    )
    for name in candidates:
        value = os.getenv(name)
        if value:
            return value
    return None


def resolve_api_keys(primary_env: str) -> list[str]:
    names = [
        primary_env,
        "OPENAI_API_KEY_BACKUP_1",
        "OPENAI_API_KEY_BACKUP_2",
    ]
    keys: list[str] = []
    for name in names:
        value = os.getenv(name)
        if value and value not in keys:
            keys.append(value)
    return keys


def resolve_base_url(fallback: str) -> str:
    return (os.getenv("OPENAI_BASE_URL") or os.getenv("DAILY_PAPER_LLM_BASE_URL") or fallback).rstrip("/")


def _parse_value(value: str) -> str:
    if not value:
        return ""
    if value[0] in {'"', "'"}:
        try:
            return shlex.split(value)[0]
        except ValueError:
            return value.strip("\"'")
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    return value
