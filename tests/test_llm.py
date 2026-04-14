import os
from pathlib import Path

from daily_paper.env import load_env_file, resolve_api_keys, resolve_model_name
from daily_paper.llm import OpenAIResponsesSummarizer
from daily_paper.models import LLMConfig


def test_extract_json_from_output_text() -> None:
    summarizer = OpenAIResponsesSummarizer(
        LLMConfig(
            enabled=False,
            provider="openai_responses",
            api_key_env="OPENAI_API_KEY",
            api_base="https://api.openai.com/v1",
            model=None,
            model_env="DAILY_PAPER_LLM_MODEL",
            reasoning_effort="low",
            timeout_seconds=30,
            max_daily_highlights=5,
            max_aggregate_papers=12,
        )
    )
    payload = {"output_text": '{"headline":"x","summary_points":["a","b","c"],"trends":["a","b","c"],"gaps":["a","b","c"],"next_actions":["a","b","c"]}'}
    parsed = summarizer._extract_json(payload)
    assert parsed["headline"] == "x"


def test_extract_json_from_chat_completions() -> None:
    summarizer = OpenAIResponsesSummarizer(
        LLMConfig(
            enabled=False,
            provider="openai_responses",
            api_key_env="OPENAI_API_KEY",
            api_base="https://api.openai.com/v1",
            model=None,
            model_env="IDEA_MODEL",
            reasoning_effort="low",
            timeout_seconds=30,
            max_daily_highlights=5,
            max_aggregate_papers=12,
        )
    )
    payload = {
        "choices": [
            {
                "message": {
                    "content": '{"headline":"x","summary_points":["a","b","c"],"trends":["a","b","c"],"gaps":["a","b","c"],"next_actions":["a","b","c"]}'
                }
            }
        ]
    }
    parsed = summarizer._extract_chat_completions_json(payload)
    assert parsed["headline"] == "x"


def test_load_env_file_and_resolvers(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        'OPENAI_API_KEY="primary"\nOPENAI_API_KEY_BACKUP_1="backup1"\nIDEA_MODEL="idea"\nEXP_MODEL="exp"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_BACKUP_1", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_BACKUP_2", raising=False)
    monkeypatch.delenv("IDEA_MODEL", raising=False)
    monkeypatch.delenv("EXP_MODEL", raising=False)
    load_env_file(env_path)
    assert os.getenv("OPENAI_API_KEY") == "primary"
    assert resolve_api_keys("OPENAI_API_KEY") == ["primary", "backup1"]
    assert resolve_model_name("IDEA_MODEL") == "idea"
