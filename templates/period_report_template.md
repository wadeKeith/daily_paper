---
report_type: {{ report_type }}
period_type: {{ period_type }}
period_label: {{ period_label }}
date_range:
  start: {{ date_range.start }}
  end: {{ date_range.end }}
generated_at: {{ generated_at }}
generator:
  repo_name: {{ generator.repo_name }}
  repo_commit: "{{ generator.repo_commit }}"
  pipeline_version: "{{ generator.pipeline_version }}"
llm:
  enabled: {{ llm.enabled | lower }}
  provider: {{ llm.provider }}
  model: "{{ llm.model }}"
  enhanced: {{ llm.enhanced | lower }}
statistics:
  reports_included: {{ statistics.reports_included }}
  papers_mentioned_total: {{ statistics.papers_mentioned_total }}
  unique_papers_total: {{ statistics.unique_papers_total }}
  highlight_mentions_total: {{ statistics.highlight_mentions_total }}
  unique_highlights_total: {{ statistics.unique_highlights_total }}
---

# {{ period_type | title }} Research Digest — {{ period_label }}

## 0. Executive Summary

- {{ executive_summary.headline }}
{% for item in executive_summary.summary_points %}
- {{ item }}
{% endfor %}

## 1. Coverage

- Date range: `{{ date_range.start }}` to `{{ date_range.end }}`
- Reports included: `{{ statistics.reports_included }}`
- Paper mentions: `{{ statistics.papers_mentioned_total }}`
- Unique papers: `{{ statistics.unique_papers_total }}`
- Highlight mentions: `{{ statistics.highlight_mentions_total }}`
- Unique highlights: `{{ statistics.unique_highlights_total }}`

## 2. Topic Distribution

- VLA: `{{ topic_counts.get("VLA", 0) }}`
- World Models: `{{ topic_counts.get("World Models", 0) }}`
- Multimodal LLMs: `{{ topic_counts.get("Multimodal LLMs", 0) }}`
- Agents: `{{ topic_counts.get("Agents", 0) }}`
- Other Relevant: `{{ topic_counts.get("Other Relevant", 0) }}`

## 3. Top Papers

{% for paper in top_papers %}
### 3.{{ loop.index }} {{ paper.title }}

- `primary_topic`: {{ paper.primary_topic }}
- `mention_count`: {{ paper.mention_count }}
- `highlight_count`: {{ paper.highlight_count }}
- `read_now_count`: {{ paper.read_now_count }}
- `reproduce_count`: {{ paper.reproduce_count }}
- `best_score`: {{ paper.best_score }}
- `avg_score`: {{ paper.avg_score }}
- `first_seen_report_date`: {{ paper.first_seen_report_date }}
- `last_seen_report_date`: {{ paper.last_seen_report_date }}
- `method_tags`: {{ paper.method_tags | join_or_null }}
- `application_tags`: {{ paper.application_tags | join_or_null }}
- `paper_url`: {{ paper.paper_url | or_unknown }}
- `code_url`: {{ paper.code_url | or_unknown }}
{% endfor %}

## 4. Trend Analysis

### 4.1 Trends
{% for item in trend_analysis.trends %}
- {{ item }}
{% endfor %}

### 4.2 Gaps
{% for item in trend_analysis.gaps %}
- {{ item }}
{% endfor %}

### 4.3 Next Actions
{% for item in trend_analysis.next_actions %}
- {{ item }}
{% endfor %}

## 5. Top Days

{% for day in top_days %}
- {{ day.report_date }} — selected `{{ day.selected_total }}`, highlights `{{ day.highlights_total }}`, top topic `{{ day.top_topic }}`
{% endfor %}

## 6. Tag Breakdown

### 6.1 Method Tags
{% if method_tag_counts %}
{% for tag, count in method_tag_counts %}
- {{ tag }}: `{{ count }}`
{% endfor %}
{% else %}
- 暂无
{% endif %}

### 6.2 Application Tags
{% if application_tag_counts %}
{% for tag, count in application_tag_counts %}
- {{ tag }}: `{{ count }}`
{% endfor %}
{% else %}
- 暂无
{% endif %}

## 7. Daily Breakdown

{% for row in daily_reports %}
- {{ row.report_date }} — selected `{{ row.selected_total }}`, highlights `{{ row.highlights_total }}`, top topic `{{ row.top_topic }}`
{% endfor %}

## 8. Appendix

### 8.1 Source Reports
{% for item in appendix.source_reports %}
- {{ item }}
{% endfor %}

### 8.2 LLM Warnings
{% if appendix.llm_warnings %}
{% for item in appendix.llm_warnings %}
- {{ item }}
{% endfor %}
{% else %}
- 无
{% endif %}
