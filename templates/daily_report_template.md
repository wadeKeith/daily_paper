---
report_type: {{ report_type }}
report_date: {{ report_date }}
timezone: {{ timezone }}
generated_at: {{ generated_at }}
generator:
  repo_name: {{ generator.repo_name }}
  repo_commit: "{{ generator.repo_commit }}"
  pipeline_version: "{{ generator.pipeline_version }}"

sources:
{% for source in sources %}
  - name: {{ source.name }}
    enabled: {{ source.enabled | lower }}
    query_groups:
{% for group in source.query_groups %}
      - {{ group }}
{% endfor %}
{% endfor %}

crawl_window:
  start: {{ crawl_window.start }}
  end: {{ crawl_window.end }}
  note: "{{ crawl_window.note }}"

statistics:
  raw_candidates_total: {{ statistics.raw_candidates_total }}
  deduplicated_total: {{ statistics.deduplicated_total }}
  selected_total: {{ statistics.selected_total }}
  highlights_total: {{ statistics.highlights_total }}

topic_counts:
  vla: {{ topic_counts.vla }}
  world_models: {{ topic_counts.world_models }}
  multimodal_llm: {{ topic_counts.multimodal_llm }}
  agents: {{ topic_counts.agents }}
  other_relevant: {{ topic_counts.other_relevant }}

selection_policy:
  included_if:
{% for item in selection_policy.included_if %}
    - "{{ item }}"
{% endfor %}
  excluded_if:
{% for item in selection_policy.excluded_if %}
    - "{{ item }}"
{% endfor %}

ranking_policy:
  highlight_score_formula: "{{ ranking_policy.highlight_score_formula }}"
  score_range: "{{ ranking_policy.score_range }}"

tags:
{% for tag in tags %}
  - {{ tag }}
{% endfor %}
---

# Daily Research Digest — {{ report_date }}

> 本日报聚焦：**VLA / 世界模型 / 多模态大模型 / 智能体**
>
> 数据来源：**arXiv / Hugging Face Papers**
>
> 统计口径：去重后只保留原始论文条目；同一论文若同时出现在多个平台，仅保留一条主记录，并在资源区中合并展示。

---

## 0. Executive Summary

### 0.1 今日一句话结论
{% for line in executive_summary.conclusion_lines %}
- {{ line }}
{% endfor %}

### 0.2 今日 Top Highlights
{% for item in executive_summary.top_highlights %}
{{ loop.index }}. **{{ item.title }}** — {{ item.reason }}
{% endfor %}

### 0.3 今日总体分布
- VLA：`{{ topic_counts.vla }}`
- World Models：`{{ topic_counts.world_models }}`
- Multimodal LLMs：`{{ topic_counts.multimodal_llm }}`
- Agents：`{{ topic_counts.agents }}`
- 其他但相关：`{{ topic_counts.other_relevant }}`

### 0.4 今日研究观察
{% for item in executive_summary.research_observations %}
- **{{ item.label }}**：{{ item.text }}
{% endfor %}

---

## 1. Report Metadata

### 1.1 抓取配置摘要
- 抓取日期：`{{ metadata_summary.report_date }}`
- 时区：`{{ metadata_summary.timezone }}`
- 生成时间：`{{ metadata_summary.generated_at }}`
- 原始候选数：`{{ metadata_summary.raw_candidates_total }}`
- 去重后数量：`{{ metadata_summary.deduplicated_total }}`
- 最终入选数量：`{{ metadata_summary.selected_total }}`

### 1.2 检索主题
{% for group in query_groups %}
- `{{ group }}`
{% endfor %}

### 1.3 检索关键词 / 查询式
```text
{% for topic_name, terms in query_terms.items() %}
[{{ topic_name }}]
{{ terms | join(" OR ") }}

{% endfor %}
```

### 1.4 去重与归并规则
- 优先使用：`arXiv canonical id`
- 次级匹配：`title normalized + first author + published date`
- 若同一论文同时出现在 arXiv 与 Hugging Face Papers：
- 主记录保留一条
- 资源链接合并到同一论文卡片下
- `source_aliases` 记录全部来源

---

## 2. Topic Overview

{% for topic in topic_overview %}
### 2.{{ loop.index }} {{ topic.name }}

今日新增：`{{ topic.count }}`

总体判断
- {{ topic.judgement }}

最值得看
{% if topic.top_papers %}
{% for title in topic.top_papers %}
- {{ title }}
{% endfor %}
{% else %}
- 暂无
{% endif %}

值得注意的共性
{% for item in topic.commonalities %}
- {{ item }}
{% endfor %}

潜在问题
{% for item in topic.pitfalls %}
- {{ item }}
{% endfor %}

---
{% endfor %}

## 3. Highlight Papers

这一节只放当天最值得读的 3~8 篇。每篇卡片字段顺序固定，方便后续自动解析。

---

{% for paper in highlight_papers %}
{% set paper_index = loop.index %}
{% include "paper_card_full_template.md" %}
{% endfor %}

## 4. Full Paper List by Topic

这一节放入选但不是 highlight 的论文，格式简化为 Lite 卡片。

{% for topic in topic_overview %}
### 4.{{ loop.index }} {{ topic.name }}

{% set bucket = paper_list_by_topic.get(topic.name, []) %}
{% if bucket %}
{% for paper in bucket %}
{% include "paper_card_lite_template.md" %}
{% endfor %}
{% else %}
- 暂无
{% endif %}
{% endfor %}

---

## 5. Cross-Paper Insights

### 5.1 今日共性趋势
{% for item in cross_paper_insights.trends %}
- {{ item }}
{% endfor %}

### 5.2 技术 motif 复现情况
{% for key, value in cross_paper_insights.motifs.items() %}
- {{ key }}: {{ value }}
{% endfor %}

### 5.3 研究空白
{% for item in cross_paper_insights.gaps %}
- {{ item }}
{% endfor %}

### 5.4 对我当前研究主线的启发
{% for item in cross_paper_insights.inspiration %}
- {{ item }}
{% endfor %}

---

## 6. Action Queue

### 6.1 Read Now
{% if action_queue.read_now %}
{% for item in action_queue.read_now %}
- {{ item.title }}
{% endfor %}
{% else %}
- 暂无
{% endif %}

### 6.2 Track
{% if action_queue.track %}
{% for item in action_queue.track %}
- {{ item.title }}
{% endfor %}
{% else %}
- 暂无
{% endif %}

### 6.3 Reproduce
{% if action_queue.reproduce %}
{% for item in action_queue.reproduce %}
- {{ item.title }}
{% endfor %}
{% else %}
- 暂无
{% endif %}

### 6.4 Ignore / Low Priority
{% if action_queue.ignore %}
{% for item in action_queue.ignore %}
- {{ item.title }} — {{ item.reason }}
{% endfor %}
{% else %}
- 暂无
{% endif %}

---

## 7. Appendix

### 7.1 Raw Candidates
{% for item in appendix.raw_candidates %}
- {{ item.title }} — {{ item.source }} / {{ item.topic }}
{% endfor %}

### 7.2 Filtered Out
{% if appendix.filtered_out %}
{% for item in appendix.filtered_out %}
- {{ item.title }} — {{ item.reason }}
{% endfor %}
{% else %}
- 无
{% endif %}

### 7.3 Deduplication Log
{% if appendix.deduplication_log %}
{% for item in appendix.deduplication_log %}
- {{ item }}
{% endfor %}
{% else %}
- 无
{% endif %}

### 7.4 Crawl Errors
{% if appendix.crawl_errors %}
{% for item in appendix.crawl_errors %}
- {{ item }}
{% endfor %}
{% else %}
- 无
{% endif %}

### 7.5 Parsing Warnings
{% if appendix.parsing_warnings %}
{% for item in appendix.parsing_warnings %}
- {{ item }}
{% endfor %}
{% else %}
- 无
{% endif %}

### 7.6 LLM Warnings
{% if appendix.llm_warnings %}
{% for item in appendix.llm_warnings %}
- {{ item }}
{% endfor %}
{% else %}
- 无
{% endif %}

### 7.7 TODO for Tomorrow
{% for item in appendix.todo_for_tomorrow %}
- {{ item }}
{% endfor %}
