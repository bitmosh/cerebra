# Round 2 Calibration — Granite 4.1 Base Models

Quick follow-up calibration to test newly-pulled Granite 4.1 base models against Round 1 results. Reuses the existing harness; just adds two models.

## Context

Round 1 ran 11 models, found Qwen 3.5 9B at 58% partial accuracy (best), Granite 4.0 Micro at 53% with 70% Pass 1 quadrant accuracy (highest of any model tested). Full results in `docs/agent/multi_model_comparison.md`.

Since then, two new models were pulled:
- `huggingface.co/unsloth/granite-4.1-3b-GGUF:Q4_K_M` (2.1GB) — Granite 4.1 3B base
- `huggingface.co/unsloth/granite-4.1-8b-GGUF:Q4_K_M` (5.3GB) — Granite 4.1 8B base

These are the dense-architecture successors to Granite 4.0. IBM positions Granite 4.1 8B as matching Granite 4.0 32B MoE performance with 4× parameter reduction. Granite 4.1 family is explicitly non-reasoning by design — no thinking chains, predictable latency. Architectural fit for Cerebra's substrate philosophy.

These are **base models** (no instruct variant available — pull failed with HuggingFace 500 error). For calibration testing this means slightly less polished prompt-following; for v0.2 LoRA training base models are actually preferred.

## Goal

Two empirical questions:

1. Does Granite 4.1 3B base beat Granite 4.0 Micro's 70% Pass 1 quadrant accuracy and 53% partial accuracy? (Tests IBM's "4.1 beats 4.0 at same size" claim on our task.)

2. Does Granite 4.1 8B base approach or exceed Qwen 3.5 9B's 58% partial accuracy? (Tests "4.1 8B matches 4.0 32B MoE" claim on our task.)

If yes to either, the Phase 2 production model decision opens up. If both yes, Granite 4.1 8B becomes the production candidate (no thinking mode, same family as v0.2 LoRA target, Apache 2.0).

## Tasks

### 1. Add LiteLLM aliases

Edit `~/Projects/ai-stack/litellm/litellm-config.yaml` and add:

```yaml
  - model_name: cerebra-classifier-granite41-3b
    litellm_params:
      model: ollama/huggingface.co/unsloth/granite-4.1-3b-GGUF:Q4_K_M
      api_base: http://ollama:11434
  
  - model_name: cerebra-classifier-granite41-8b
    litellm_params:
      model: ollama/huggingface.co/unsloth/granite-4.1-8b-GGUF:Q4_K_M
      api_base: http://ollama:11434
```

(Adjust paths to match how Round 1 aliases were configured. Round 1 ultimately bypassed LiteLLM for the OllamaDirectAdapter — if that pattern continues, just add the model identifiers to the calibration script's model list.)

Restart LiteLLM container if config changed.

### 2. Update calibration script

In `scripts/experimental/multi_model_calibration.py`, add to the model list:

```python
MODELS_TO_TEST = [
    # ... existing Round 1 models if you want to re-run for comparison ...
    "cerebra-classifier-granite41-3b",
    "cerebra-classifier-granite41-8b",
]
```

OR if you only want to test the new models (faster, since Round 1 data is already in the report), set `MODELS_TO_TEST` to just the two new ones for this run.

### 3. Run calibration

Same settings as Round 1: temperature 0.0, think:false (Granite 4.1 has no thinking mode but set it anyway for consistency), v0.1.0 two-pass prompts (PROMPT_VERSION 2.0.0), 30 fixtures with the 4 ambiguous markings, 3 runs per model.

```bash
python scripts/experimental/multi_model_calibration.py
```

### 4. Verify same metrics captured as Round 1

For each model, capture:
- Strict accuracy (X/30)
- Partial-credit accuracy (X.5/30)
- Clear / Ambiguous / Hard breakdown
- 4-quadrant table (high/low confidence × correct/wrong)
- Per-call latency: min, max, mean, p50, p95
- Pass 1 quadrant accuracy
- Pass 2 within-quadrant accuracy (conditional on Pass 1 correct)
- Per-D1-category accuracy
- JSON parse failure rate
- Run-to-run variance (should be 0.0% at temp 0.0 per Round 1)
- VRAM used during inference

### 5. Write Round 2 results doc

Create `docs/agent/multi_model_comparison_round2.md` with:

**Section 1: Round 2 results table** — same columns as Round 1's summary table, with the two new models. Include the comparison baselines (Qwen 3.5 9B, Granite 4.0 Micro) at the top for easy comparison.

**Section 2: Detailed sections** for each of the two new models — same format as Round 1.

**Section 3: Head-to-head comparisons**:
- Granite 4.1 3B vs Granite 4.0 Micro (does 4.1 beat 4.0 at same size?)
- Granite 4.1 8B vs Qwen 3.5 9B (does 4.1 dense match Qwen 9B?)
- Granite 4.1 8B vs Granite 4.0 32B MoE (validates IBM's claim if we have data, otherwise note we can't test the 32B at 12GB)

**Section 4: Updated recommendation**:
- If a Granite 4.1 variant clearly outperforms current production (Qwen 3.5 9B): recommend switching production model
- If they're competitive but not better: recommend keeping Qwen 9B for v0.1.0 ship, switching to Granite 4.1 8B in v0.1.1 after LoRA training validates the substrate
- If they underperform significantly: recommend sticking with current plan
- Either way, recommend Granite 4.1 (3B or 8B) as a v0.2 LoRA candidate alongside OLMo 3 7B

### 6. Update raw JSON

Append Round 2 results to `multi_model_comparison_raw.json` or create `multi_model_comparison_raw_round2.json`. Whichever fits the existing structure.

### 7. Cross-model agreement update

For Round 2 models, note which of the 5 consensus-failure fixtures (clear_07, clear_11, hard_02, hard_07, hard_11) the new models got right or wrong. If Granite 4.1 gets any of these right where the 11 Round 1 models failed, that's diagnostic signal about what specific capability Granite 4.1 has that others lack.

## Estimated runtime

- 2 models × 3 runs × ~30 chunks × ~3-5s per chunk = ~30-50 minutes total compute
- Plus writeup time
- Should complete in under an hour of mostly-unattended work

## What's NOT in scope

- Do NOT make the production model switch as part of this pass (data only)
- Do NOT re-run Round 1 models unless something has changed that would invalidate their results
- Do NOT iterate on the v2.0.0 prompts
- Do NOT touch the fixture set

This pass produces data for a decision. The decision happens separately based on the data.

## After this completes

Two questions for the user to decide:

1. **Phase 2 production model:** stay on Qwen 3.5 9B or switch to a Granite 4.1 variant?
2. **v0.2 LoRA target:** Granite 4.1 3B, Granite 4.1 8B, OLMo 3 7B, or multi-candidate parallel training?

Report findings; user decides; next pass implements whatever was decided.
