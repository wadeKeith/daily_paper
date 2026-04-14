from __future__ import annotations

import argparse
from dataclasses import replace
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from daily_paper.aggregate import AggregatePipeline
from daily_paper.config import load_config
from daily_paper.env import load_env_file
from daily_paper.pipeline import DigestPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a daily AI paper digest.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generate the daily markdown and JSON report.")
    generate.add_argument("--report-date", type=str, help="Report date in YYYY-MM-DD. Defaults to today in config timezone.")
    generate.add_argument("--timezone", type=str, help="Override timezone from config.")
    generate.add_argument("--config", type=str, help="Path to YAML config.")
    generate.add_argument("--output-dir", type=str, default="reports/daily", help="Directory for generated reports.")
    generate.add_argument("--enable-llm", action="store_true", help="Force enable LLM summarizer for this run.")
    generate.add_argument("--disable-llm", action="store_true", help="Force disable LLM summarizer for this run.")

    weekly = subparsers.add_parser("aggregate-weekly", help="Aggregate daily JSON reports into a weekly digest.")
    weekly.add_argument("--anchor-date", type=str, help="Any YYYY-MM-DD inside the target ISO week. Defaults to today.")
    weekly.add_argument("--timezone", type=str, help="Override timezone from config.")
    weekly.add_argument("--config", type=str, help="Path to YAML config.")
    weekly.add_argument("--input-dir", type=str, default="reports/daily", help="Directory containing daily JSON reports.")
    weekly.add_argument("--output-dir", type=str, default="reports/weekly", help="Directory for aggregated weekly reports.")
    weekly.add_argument("--enable-llm", action="store_true", help="Force enable LLM summarizer for this run.")
    weekly.add_argument("--disable-llm", action="store_true", help="Force disable LLM summarizer for this run.")

    monthly = subparsers.add_parser("aggregate-monthly", help="Aggregate daily JSON reports into a monthly digest.")
    monthly.add_argument("--anchor-date", type=str, help="Any YYYY-MM-DD inside the target month. Defaults to today.")
    monthly.add_argument("--month", type=str, help="Target month in YYYY-MM format.")
    monthly.add_argument("--timezone", type=str, help="Override timezone from config.")
    monthly.add_argument("--config", type=str, help="Path to YAML config.")
    monthly.add_argument("--input-dir", type=str, default="reports/daily", help="Directory containing daily JSON reports.")
    monthly.add_argument("--output-dir", type=str, default="reports/monthly", help="Directory for aggregated monthly reports.")
    monthly.add_argument("--enable-llm", action="store_true", help="Force enable LLM summarizer for this run.")
    monthly.add_argument("--disable-llm", action="store_true", help="Force disable LLM summarizer for this run.")
    return parser


def _resolve_config(config_path: str | None, timezone: str | None, enable_llm: bool, disable_llm: bool):
    config = load_config(config_path)
    if timezone:
        config.timezone = timezone
    if enable_llm and disable_llm:
        raise ValueError("--enable-llm and --disable-llm cannot be used together")
    if enable_llm:
        config.llm = replace(config.llm, enabled=True)
    if disable_llm:
        config.llm = replace(config.llm, enabled=False)
    return config


def _write_report(report: dict, output_dir: str | Path, stem_name: str) -> tuple[Path, Path]:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = target_dir / stem_name
    markdown_path = stem.with_suffix(".md")
    json_path = stem.with_suffix(".json")
    markdown_path.write_text(report["markdown"], encoding="utf-8")
    json_path.write_text(json.dumps(report["json"], ensure_ascii=False, indent=2), encoding="utf-8")
    return markdown_path, json_path


def main() -> None:
    load_env_file()
    parser = build_parser()
    args = parser.parse_args()
    config = _resolve_config(
        getattr(args, "config", None),
        getattr(args, "timezone", None),
        getattr(args, "enable_llm", False),
        getattr(args, "disable_llm", False),
    )
    timezone = config.timezone

    if args.command == "generate":
        if args.report_date:
            report_date = date.fromisoformat(args.report_date)
        else:
            report_date = datetime.now(ZoneInfo(timezone)).date()
        pipeline = DigestPipeline(config=config)
        report = pipeline.generate(report_date=report_date, timezone=timezone)
        markdown_path, json_path = _write_report(report, args.output_dir, report_date.isoformat())
    elif args.command == "aggregate-weekly":
        anchor_date = date.fromisoformat(args.anchor_date) if args.anchor_date else datetime.now(ZoneInfo(timezone)).date()
        pipeline = AggregatePipeline(config=config)
        report = pipeline.aggregate_weekly(anchor_date=anchor_date, input_dir=args.input_dir)
        markdown_path, json_path = _write_report(report, args.output_dir, report["json"]["period_label"])
    elif args.command == "aggregate-monthly":
        if args.month:
            anchor_date = date.fromisoformat(f"{args.month}-01")
        else:
            anchor_date = date.fromisoformat(args.anchor_date) if args.anchor_date else datetime.now(ZoneInfo(timezone)).date()
        pipeline = AggregatePipeline(config=config)
        report = pipeline.aggregate_monthly(anchor_date=anchor_date, input_dir=args.input_dir)
        markdown_path, json_path = _write_report(report, args.output_dir, report["json"]["period_label"])
    else:
        raise ValueError(f"Unsupported command: {args.command}")

    print(markdown_path)
    print(json_path)


if __name__ == "__main__":
    main()
