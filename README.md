# Daily AI Paper Digest

一个面向 `VLA / World Models / Multimodal LLMs / Agents` 的日报仓库。它每天从 `arXiv` 和 `HuggingFace Papers` 拉取论文候选，做去重、主题归类、资源补全、打分，然后同时输出：

- `reports/daily/YYYY-MM-DD.md`
- `reports/daily/YYYY-MM-DD.json`

目标不是做“全自动完美摘要”，而是先把稳定的数据抓取、结构化模板和每天可复用的研究节奏搭起来。

## 功能

- 官方接口优先
  - arXiv: `export.arxiv.org/api/query` Atom API
  - Hugging Face: `GET /api/papers`、`GET /api/daily_papers`、`GET /api/papers/{arxiv_id}`、`GET /api/arxiv/{arxiv_id}/repos`
- 多来源去重
  - 优先用 `arxiv_id`
  - 兜底用 `normalized title + first author + published date`
- 主题分类
  - `VLA`
  - `World Models`
  - `Multimodal LLMs`
  - `Agents`
  - `Other Relevant`
- Markdown + JSON 双输出
- 可直接放到 GitHub Actions 每天定时跑

## 目录

```text
.
├── config/topics.yaml
├── templates/
│   ├── daily_report_template.md
│   ├── paper_card_full_template.md
│   └── paper_card_lite_template.md
├── src/daily_paper/
│   ├── aggregate.py
│   ├── classification.py
│   ├── cli.py
│   ├── config.py
│   ├── llm.py
│   ├── models.py
│   ├── pipeline.py
│   ├── render.py
│   └── sources/
│       ├── arxiv.py
│       └── huggingface.py
├── reports/daily/
└── .github/workflows/daily_digest.yml
```

## 安装

推荐用 `uv`，直接 editable 运行：

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

也可以直接：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 生成日报

默认用 `config/topics.yaml` 里的时区和当天日期：

```bash
daily-paper generate
```

指定日期：

```bash
daily-paper generate --report-date 2026-04-14
```

指定输出目录：

```bash
daily-paper generate --report-date 2026-04-14 --output-dir reports/daily
```

如果你只想临时关闭或开启 LLM 增强：

```bash
daily-paper generate --report-date 2026-04-14 --disable-llm
daily-paper generate --report-date 2026-04-14 --enable-llm
```

## 生成周报 / 月报

按任意一个落在目标周期内的日期聚合周报：

```bash
daily-paper aggregate-weekly --anchor-date 2026-04-14
```

按月份聚合月报：

```bash
daily-paper aggregate-monthly --month 2026-04
```

输出路径固定为：

- `reports/weekly/YYYY-Www.md`
- `reports/weekly/YYYY-Www.json`
- `reports/monthly/YYYY-MM.md`
- `reports/monthly/YYYY-MM.json`

## LLM Summarizer

默认关闭。启用后，它会只增强这些“判断性字段”：

- 日报首页的 `Executive Summary`
- 高亮论文卡片里的 `one_line_summary / why_read_today / strengths / weaknesses / open_questions / my_take`
- 周报/月报的 `headline / summary_points / trends / gaps / next_actions`

不会影响：

- 数据抓取
- 去重
- 主题分类
- 文件输出

也就是说，即使 LLM 配置错了，日报/周报/月报仍然会照常生成，只是在 `Appendix -> LLM Warnings` 里留下诊断信息。

仓库会自动加载根目录 `.env`，所以默认不需要手动 `export`。

启用方式：

1. 在 [config/topics.yaml](/Users/yin/Documents_local/Github/daily_paper/config/topics.yaml) 里把 `llm.enabled` 设为 `true`
2. 在根目录 `.env` 里维护模型和 key

```bash
OPENAI_BASE_URL=...
OPENAI_API_KEY=...
IDEA_MODEL=...
```

当前实现会优先从 `.env` 读取：

- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_API_KEY_BACKUP_1`
- `OPENAI_API_KEY_BACKUP_2`
- `IDEA_MODEL`
- `EXP_MODEL`

## 配置

主配置文件在 [config/topics.yaml](/Users/yin/Documents_local/Github/daily_paper/config/topics.yaml)。

你可以直接改：

- 报告时区
- 回溯窗口天数
- 每个主题的查询词
- 主题分类关键词
- 每个主题最多保留多少篇
- 打分公式说明文字
- LLM 是否启用、模型名、超时和增强范围上限
- 周报/月报的 top papers / top tags 保留数量

## 当前实现边界

- `one_line_summary`、`Structured Summary`、`My Take` 目前是规则生成，不是 LLM 精读级别分析。
- Hugging Face 资源补全依赖 paper page 和 `arxiv/{id}/repos`，资源质量取决于社区是否已经关联。
- arXiv 查询是按 topic query 拉取近期结果再本地过滤时间窗口，不是服务端日期精确检索。

这套实现的重点是“先稳定产出”，不是在第一版里做过拟合的自动评论。

## GitHub Actions

仓库已经带了定时任务：

- 每天按 `Asia/Shanghai` 的晚间时间生成日报
- 每周一自动为上一完整周生成周报
- 每月 1 日自动为上一完整月生成月报
- 自动提交 `reports/daily/*.md` 和 `reports/daily/*.json`
- 自动提交 `reports/weekly/*` 和 `reports/monthly/*`

如果你要改跑批时间，只改 [.github/workflows/daily_digest.yml](/Users/yin/Documents_local/Github/daily_paper/.github/workflows/daily_digest.yml) 就够了。

## 后续建议

如果你要继续把仓库做厚，优先顺序建议是：

1. 把日/周/月报的 JSON schema 单独固化出来并做校验
2. 给聚合层增加“重复出现论文”的跨周期跟踪视图
3. 把 topic / method / application tags 再细化成矩阵统计
4. 给高亮论文加入人工覆写层

## 参考

- [arXiv API User's Manual](https://info.arxiv.org/help/api/user-manual.html)
- [Hugging Face Paper Pages](https://huggingface.co/docs/hub/paper-pages)
- [Hugging Face Hub API Endpoints](https://huggingface.co/docs/hub/main/api)
