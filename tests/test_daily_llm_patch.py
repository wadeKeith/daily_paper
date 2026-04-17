from daily_paper.config import load_config
from daily_paper.pipeline import DigestPipeline


def test_daily_llm_patch_skips_invalid_overrides(monkeypatch) -> None:
    class FakeSummarizer:
        def __init__(self, _config) -> None:
            pass

        def status(self):
            return type("Status", (), {"available": True, "reason": None})()

        def enhance_daily_report(self, _report_json):
            return {
                "conclusion_lines": ["结论 1", "结论 2", "结论 3"],
                "research_observations": [
                    {"label": "趋势 1", "text": "A"},
                    {"label": "趋势 2", "text": "B"},
                    {"label": "趋势 3", "text": "C"},
                    {"label": "空白点 / 机会点", "text": "D"},
                ],
                "paper_overrides": [
                    "unexpected-string",
                    {
                        "paper_id": "paper-1",
                        "one_line_summary": "新的单行总结",
                        "why_read_today": "新的阅读理由",
                        "strengths": ["优点"],
                        "weaknesses": ["缺点"],
                        "open_questions": ["问题"],
                        "what_can_i_borrow": "可借鉴点",
                        "what_do_i_not_buy": "不认同点",
                    },
                ],
                "cross_paper_insights": {
                    "trends": ["T1", "T2", "T3"],
                    "gaps": ["G1", "G2", "G3"],
                    "inspiration": ["I1", "I2", "I3"],
                },
            }

    monkeypatch.setattr("daily_paper.pipeline.OpenAIResponsesSummarizer", FakeSummarizer)

    pipeline = DigestPipeline(load_config())
    report_json = {
        "executive_summary": {
            "conclusion_lines": ["旧结论 1", "旧结论 2", "旧结论 3"],
            "research_observations": [
                {"label": "趋势 1", "text": "旧A"},
                {"label": "趋势 2", "text": "旧B"},
                {"label": "趋势 3", "text": "旧C"},
                {"label": "空白点 / 机会点", "text": "旧D"},
            ],
            "top_highlights": [{"title": "Paper 1", "reason": "旧理由"}],
        },
        "highlight_papers": [
            {
                "paper_id": "paper-1",
                "title": "Paper 1",
                "one_line_summary": "旧总结",
                "why_read_today": "旧阅读理由",
                "strengths": ["旧优点"],
                "weaknesses": ["旧缺点"],
                "open_questions": ["旧问题"],
                "my_take": {
                    "what_can_i_borrow": "旧可借鉴点",
                    "what_do_i_not_buy": "旧不认同点",
                },
            }
        ],
        "cross_paper_insights": {
            "trends": ["旧T1", "旧T2", "旧T3"],
            "gaps": ["旧G1", "旧G2", "旧G3"],
            "inspiration": ["旧I1", "旧I2", "旧I3"],
        },
        "llm": {"enhanced": False},
    }
    llm_warnings: list[str] = []

    pipeline._maybe_llm_enhance_daily_report(report_json, llm_warnings)

    assert report_json["executive_summary"]["conclusion_lines"] == ["结论 1", "结论 2", "结论 3"]
    assert report_json["highlight_papers"][0]["why_read_today"] == "新的阅读理由"
    assert report_json["executive_summary"]["top_highlights"][0]["reason"] == "新的阅读理由"
    assert report_json["cross_paper_insights"]["trends"] == ["T1", "T2", "T3"]
    assert report_json["llm"]["enhanced"] is True
    assert llm_warnings == ["LLM daily enhancement returned 1 invalid paper_overrides item(s); skipped them."]
