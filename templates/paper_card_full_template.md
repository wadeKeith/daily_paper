### 3.{{ paper_index }} {{ paper.title }}

**Basic Info**
- `paper_id`: {{ paper.paper_id }}
- `title`: {{ paper.title }}
- `authors`: {{ paper.authors | join_or_null }}
- `first_author`: {{ paper.first_author }}
- `source_primary`: {{ paper.source_primary }}
- `source_aliases`: {{ paper.source_aliases | join_or_null }}
- `arxiv_id`: {{ paper.arxiv_id | or_unknown }}
- `version`: {{ paper.version | or_unknown }}
- `hf_paper_url`: {{ paper.hf_paper_url | or_unknown }}
- `paper_url`: {{ paper.paper_url | or_unknown }}
- `pdf_url`: {{ paper.pdf_url | or_unknown }}
- `project_url`: {{ paper.project_url | or_unknown }}
- `code_url`: {{ paper.code_url | or_unknown }}
- `published_at`: {{ paper.published_at | or_unknown }}
- `updated_at`: {{ paper.updated_at | or_unknown }}
- `primary_category`: {{ paper.primary_category | or_unknown }}
- `categories`: {{ paper.categories | join_or_null }}
- `institution_hint`: {{ paper.institution_hint | or_unknown }}
- `license_hint`: {{ paper.license_hint | or_unknown }}
- `comment`: {{ paper.comment | or_unknown }}
- `journal_ref`: {{ paper.journal_ref | or_unknown }}
- `doi`: {{ paper.doi | or_unknown }}

**Fast Verdict**
- `one_line_summary`: {{ paper.one_line_summary }}
- `why_read_today`: {{ paper.why_read_today }}
- `relevance_level`: {{ paper.relevance_level }}
- `highlight_score`: {{ paper.highlight_score | round2 }}
- `recommended_action`: {{ paper.recommended_action }}

**Structured Summary**
- `Problem`: {{ paper.structured_summary.problem }}
- `Motivation`: {{ paper.structured_summary.motivation }}
- `Core Idea`: {{ paper.structured_summary.core_idea }}
- `Method`: {{ paper.structured_summary.method }}
- `Training`: {{ paper.structured_summary.training }}
- `Inference`: {{ paper.structured_summary.inference }}
- `Evaluation`: {{ paper.structured_summary.evaluation }}
- `Main Results`: {{ paper.structured_summary.main_results }}
- `Claim`: {{ paper.structured_summary.claim }}

**Research Tags**
- `topics`: {{ paper.topics | join_or_null }}
- `method_tags`: {{ paper.method_tags | join_or_null }}
- `application_tags`: {{ paper.application_tags | join_or_null }}

**Deep Reading Notes**
- `Novelty`: {{ paper.novelty_points | join_or_null }}
- `Strengths`: {{ paper.strengths | join_or_null }}
- `Weaknesses`: {{ paper.weaknesses | join_or_null }}
- `Assumptions`: {{ paper.assumptions | join_or_null }}
- `Risks`: {{ paper.risks | join_or_null }}
- `Open Questions`: {{ paper.open_questions | join_or_null }}
- `Relation to Prior Work`: {{ paper.relation_to_prior_work }}

**Domain-Specific Analysis**
- `VLA / embodiment`: {{ paper.domain_analysis.vla.embodiment }}
- `VLA / action_space`: {{ paper.domain_analysis.vla.action_space }}
- `VLA / control_level`: {{ paper.domain_analysis.vla.control_level }}
- `VLA / memory_usage`: {{ paper.domain_analysis.vla.memory_usage }}
- `VLA / planner_usage`: {{ paper.domain_analysis.vla.planner_usage }}
- `VLA / reasoner_usage`: {{ paper.domain_analysis.vla.reasoner_usage }}
- `VLA / world_model_usage`: {{ paper.domain_analysis.vla.world_model_usage }}
- `VLA / real_robot`: {{ paper.domain_analysis.vla.real_robot }}
- `VLA / simulator`: {{ paper.domain_analysis.vla.simulator }}
- `VLA / data_source`: {{ paper.domain_analysis.vla.data_source }}
- `World Models / state_representation`: {{ paper.domain_analysis.world_models.state_representation }}
- `World Models / prediction_target`: {{ paper.domain_analysis.world_models.prediction_target }}
- `World Models / horizon`: {{ paper.domain_analysis.world_models.horizon }}
- `World Models / planning_interface`: {{ paper.domain_analysis.world_models.planning_interface }}
- `World Models / control_coupling`: {{ paper.domain_analysis.world_models.control_coupling }}
- `MLLM / modalities`: {{ paper.domain_analysis.multimodal_llms.modalities | join_or_null }}
- `MLLM / reasoning_type`: {{ paper.domain_analysis.multimodal_llms.reasoning_type }}
- `MLLM / long_context_usage`: {{ paper.domain_analysis.multimodal_llms.long_context_usage }}
- `MLLM / grounding_method`: {{ paper.domain_analysis.multimodal_llms.grounding_method }}
- `Agents / agent_type`: {{ paper.domain_analysis.agents.agent_type }}
- `Agents / tooling`: {{ paper.domain_analysis.agents.tooling }}
- `Agents / memory_type`: {{ paper.domain_analysis.agents.memory_type }}
- `Agents / planning_style`: {{ paper.domain_analysis.agents.planning_style }}
- `Agents / verification_style`: {{ paper.domain_analysis.agents.verification_style }}

**Resource Links**
- `Paper`: {{ paper.paper_url | or_unknown }}
- `PDF`: {{ paper.pdf_url | or_unknown }}
- `Code`: {{ paper.code_url | or_unknown }}
- `Project`: {{ paper.project_url | or_unknown }}
- `Model`: {{ paper.model_url | or_unknown }}
- `Dataset`: {{ paper.dataset_url | or_unknown }}
- `Demo / Space`: {{ paper.demo_url | or_unknown }}
- `Code available`: {{ paper.reproducibility.code_available | yesno }}
- `Weights available`: {{ paper.reproducibility.weights_available | yesno }}
- `Dataset available`: {{ paper.reproducibility.dataset_available | yesno }}
- `Env instructions available`: {{ paper.reproducibility.env_instructions_available | yesno }}
- `Repro effort estimate`: {{ paper.reproducibility.repro_effort_estimate }}

**My Take**
- `Should I read it?`: {{ paper.my_take.should_i_read_it }}
- `Should I reproduce it?`: {{ paper.my_take.should_i_reproduce_it }}
- `What can I borrow?`: {{ paper.my_take.what_can_i_borrow }}
- `What do I not buy?`: {{ paper.my_take.what_do_i_not_buy }}
- `Best use case`: {{ paper.my_take.best_use_case }}

---
