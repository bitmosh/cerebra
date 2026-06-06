# smol-training-mcp — MCP Server Plan

> Derived from: *The Smol Training Playbook: The Secrets to Building World-Class LLMs* (Hugging Face, Oct. 2025)

## What it is

An MCP server that encodes the Smol Training Playbook's decision frameworks, reference knowledge, config templates, and diagnostic logic as callable tools. Any agent with MCP access can use it to navigate training decisions without needing to re-read the playbook or rely on hallucinated conventions.

---

## Architecture Overview

```
smol-training-mcp/
├── server.py              # MCP entry point, tool registry
├── knowledge/
│   ├── architectures.json # Baseline model table, attention trade-offs
│   ├── frameworks.json    # Megatron/DeepSpeed/TorchTitan/Nanotron matrix
│   ├── benchmarks.json    # Evaluation suite definitions
│   └── data_sources.json  # Dataset catalog, mixing priors
├── tools/
│   ├── compass.py         # Training decision trees
│   ├── architect.py       # Architecture selection + param estimation
│   ├── ablations.py       # Ablation planner + cost estimator
│   ├── configs.py         # YAML config generator (Nanotron-first)
│   ├── posttraining.py    # SFT/DPO/GRPO routing
│   ├── infra.py           # Parallelism + GPU planning
│   └── diagnostics.py     # Loss spike + failure classification
└── templates/
    └── nanotron_base.yaml.j2
```

---

## Tool Manifest

### 1. Training Compass Tools

These encode the playbook's Why → What → How flowchart.

| Tool | Input | Output |
|------|-------|--------|
| `should_i_train` | use_case description, constraints | Decision: prompt / finetune / pretrain + rationale |
| `classify_training_goal` | goal description | Category: research / production / strategic_oss |
| `map_goal_to_specs` | goal category, constraints (latency, device, multilingual, etc.) | `{arch_type, param_range, context_len, data_requirements}` |

The `should_i_train` tool directly mirrors the flowchart: prompting → fine-tuning → scratch training, with explicit off-ramps at each node.

---

### 2. Architecture Advisor Tools

| Tool | Input | Output |
|------|-------|--------|
| `recommend_baseline` | param_target (e.g. "3B"), arch_type hint | Top 2-3 baseline models from the reference table (Llama 3.x, Qwen3, SmolLM family, MoE families) |
| `select_attention` | param_count, context_len, deployment_target | Recommended mechanism (GQA ratio, or MLA for extreme KV compression), with KV cache size formula |
| `estimate_parameters` | hidden_size, layers, heads, kv_heads, vocab_size, tied_embeddings | Parameter count breakdown by component |
| `score_architecture_change` | change description, training_goal | Is this worth ablating? Score + reasoning based on playbook heuristics |
| `recommend_masking_strategy` | doc_length_distribution, context_target | causal / intra-document + explanation |

The `estimate_parameters` tool encodes the parameter count formula from the playbook exactly — extended to MoE and hybrid cases.

---

### 3. Ablation Planner

| Tool | Input | Output |
|------|-------|--------|
| `design_ablation` | target_model_size, compute_budget_gpu_hours, training_goal | Ablation model size/tokens, proxy model recommendation if needed |
| `select_evaluation_suite` | capabilities (multilingual, math, code, reasoning, long_ctx) | Benchmark set with formulations (CF vs MCF vs FG), evaluation order |
| `estimate_ablation_cost` | model_size, tokens, gpu_type, num_gpus | GPU hours + estimated wall clock |
| `validate_ablation_plan` | ablation config | Checklist against rules of engagement (one change at a time, sufficient token count, eval coverage) |

The ablation cost tool uses the playbook's actual SmoLLM3 numbers as calibration anchors — 437K total GPU hours with ablations consuming ~37% of that.

---

### 4. Config Generator

| Tool | Input | Output |
|------|-------|--------|
| `generate_nanotron_config` | model spec, data sources + weights, optimizer choice, hardware | Complete YAML config matching the playbook's structure (data_stages / model / optimizer / parallelism / tokenizer / tokens sections) |
| `suggest_config_section` | section_name, params | Valid sub-config with documented reasoning |
| `diff_configs` | config_a, config_b | What changed, whether it's a valid single-variable ablation |

High-value for agents — they can generate a runnable Nanotron config rather than guessing field names.

---

### 5. Framework Selector

| Tool | Input | Output |
|------|-------|--------|
| `select_framework` | team_size, arch_type, need_for_custom_features, maturity_requirement | Ranked recommendations: Megatron-LM / DeepSpeed / TorchTitan / Nanotron |
| `compare_frameworks` | framework_a, framework_b | Feature matrix diff from playbook table |

---

### 6. Post-training Advisor

*(Extends into the post-training sections of the playbook)*

| Tool | Input | Output |
|------|-------|--------|
| `select_posttraining_method` | goal (instruction following / reasoning / preferences) | SFT → DPO → GRPO routing with when-to-use guidance |
| `design_sft_pipeline` | base_model, dataset_type, compute_budget | SFT config sketch |
| `design_rl_pipeline` | base_model, reward_type (verifiable/preference) | GRPO vs DPO recommendation + hyperparameter priors |
| `assess_model_merge_viability` | models list, merge_goal | When merging makes sense vs. continued training |

---

### 7. Infrastructure Planner

| Tool | Input | Output |
|------|-------|--------|
| `plan_parallelism` | model_size, num_gpus, gpu_memory_gb | Recommended DP / TP / PP settings |
| `estimate_gpu_requirements` | model_size, training_tokens, timeline_days | Minimum GPU count + compute hours |
| `diagnose_loss_spike` | spike_description, training_step, recent_changes | Likely cause + remediation from playbook's real incident log |

---

### 8. Data Curation

| Tool | Input | Output |
|------|-------|--------|
| `recommend_data_mix` | target_capabilities, model_size | Dataset names + mixing weights (FineWeb-Edu, FineMath, Python-Edu priors) |
| `explain_data_quality_trap` | dataset_name | Whether this dataset is a known high-quality-but-wrong trap (e.g. the arXiv example from the playbook) |

---

## Resources (Static MCP Resources)

Read-only reference objects served alongside tools:

| Resource URI | Contents |
|---|---|
| `resource://baselines` | Architecture baseline table (Dense/MoE/Hybrid with sizes and families) |
| `resource://benchmarks` | Full benchmark catalog — domain, task type, question count, formulation |
| `resource://attention-tradeoffs` | KV cache formulas per attention mechanism |
| `resource://ablation-rules` | The "rules of engagement" checklist verbatim from the playbook |

---

## Implementation Notes

**Language:** Python with the `mcp` SDK.

**Knowledge layer:** All reference tables stored as structured JSON so tools can query them without hitting an LLM — fast, deterministic, testable.

**Decision trees:** Implemented as pure Python functions with typed inputs/outputs, not prompt-based. The compass flowchart maps directly to `if/elif` chains with explicit return types.

**Config generation:** Jinja2 templates for the Nanotron YAML structure from the playbook. The generator validates required sections before emitting.

**Parameter estimation:** Pure math (no model inference), directly encoding the formulas from the playbook (pages 14-15).

**Scope boundary:** The server is a *knowledge and decision tool*, not a training runner. It does not shell out, does not call HuggingFace APIs, does not manage GPU clusters. Those integrations belong in separate tools.

---

## Phased Build

### Phase 1 — Core decision + reference tools (highest leverage for agents)
- `should_i_train`, `map_goal_to_specs`, `recommend_baseline`
- `select_attention`, `estimate_parameters`
- All static resources

### Phase 2 — Ablation + config generation
- `design_ablation`, `select_evaluation_suite`, `estimate_ablation_cost`
- `generate_nanotron_config`

### Phase 3 — Post-training + diagnostics
- Full post-training tool suite (requires reading playbook pages 31+)
- `diagnose_loss_spike`, `plan_parallelism`

---

## Source

Playbook authors: Loubna Ben Allal, Lewis Tunstall, Nouamane Tazi, Elie Bakouch, Ed Beeching, Carlos Miguel Patiño, Clémentine Fourrier, Thibaud Frere, Anton Lozhkov, Colin Raffel, Leandro von Werra, Thomas Wolf — Hugging Face, Oct. 30, 2025.

PDF: `docs/the-smol-training-playbook-the-secrets-to-building-world-class-llms.pdf`
