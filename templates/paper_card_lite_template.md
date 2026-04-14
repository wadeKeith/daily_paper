#### {{ paper.title }}

- **arXiv**: {{ paper.arxiv_id | or_unknown }}
- **Authors**: {{ paper.authors | join_or_null }}
- **Topic**: {{ paper.primary_topic }}
- **Summary**: {{ paper.one_line_summary }}
- **Method Tags**: {{ paper.method_tags | join_or_null }}
- **Why it matters**: {{ paper.why_read_today }}
- **Links**: [paper]({{ paper.paper_url }}){% if paper.pdf_url %} | [pdf]({{ paper.pdf_url }}){% endif %}{% if paper.code_url %} | [code]({{ paper.code_url }}){% endif %}
- **Action**: `{{ paper.recommended_action }}`

