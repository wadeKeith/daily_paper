from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from daily_paper.utils import repo_root


def _template_environment(template_dir: str | Path | None = None) -> Environment:
    root = Path(template_dir) if template_dir else repo_root() / "templates"
    env = Environment(loader=FileSystemLoader(root), autoescape=False, trim_blocks=False, lstrip_blocks=False)
    env.filters["iso"] = lambda value: value.isoformat() if hasattr(value, "isoformat") else (value or "null")
    env.filters["yesno"] = lambda value: "yes" if value else "no"
    env.filters["join_or_null"] = lambda value, sep=", ": sep.join(value) if value else "null"
    env.filters["or_unknown"] = lambda value: value if value not in (None, "", []) else "unknown"
    env.filters["round2"] = lambda value: f"{value:.2f}" if isinstance(value, float) else value
    return env


def render_markdown(report: dict[str, Any], template_name: str = "daily_report_template.md") -> str:
    env = _template_environment()
    return env.get_template(template_name).render(**report).rstrip() + "\n"

