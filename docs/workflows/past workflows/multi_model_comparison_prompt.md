# Multi-Model Calibration Comparison

Run the v0.1.0 two-pass calibration against multiple LLM backends and produce side-by-side comparison data to inform: (a) Phase 2 production model choice, (b) v0.2 LoRA training target choice.

## When to run this

After Phase 2 close-out (`phase2_closeout_prompt.md`) completes and v0.1.0 is merged. This is a separate pass to inform future decisions, not part of v0.1.0 itself.

## Goal

Empirical answer to: "Which available local model is the best substrate for Cerebra's SKU classifier task?"

Not benchmark performance. Not Intelligence Index. Cerebra-specific calibration test results.

## Models to test

Pulled models (verify with `ollama list`):

**Currently pulled (per recent ollama list):**
- `qwen3.5:latest` (6.6GB, Qwen 3.5 9B) — current production model
- `qwen3.5:4b` (3.4GB)
- `llama3.1:8b` (4.9GB)
- `hermes3:latest` (4.7GB)
- `olmo-3:7b` (4.5GB) — just pulled

**Pull if not already present (using exact tags below):**
```bash
ollama pull ibm/granite4:tiny-h        # ~4-5GB, MoE
ollama pull ibm/granite4:micro          # ~2GB, dense 3B
ollama pull huggingface.co/HuggingFaceTB/SmolLM3-3B-GGUF  # ~2GB
# Note: the hf.co domain alias has a redirect bug in Ollama; use huggingface.co
```

If a SmolLM3 pull fails, try:
```bash
ollama pull hf.co/unsloth/SmolLM3-3B-GGUF:Q4_K_M
# or
ollama pull hf.co/bartowski/SmolLM3-3B-GGUF:Q4_K_M
```

**Final pulled set (target):**
- qwen3.5:latest (9B baseline — what we already have data for)
- qwen3.5:4b
- llama3.1:8b
- olmo-3:7b
- ibm/granite4:tiny-h (~7B MoE)
- ibm/granite4:micro (~3B dense)
- smollm3-3b (or however it's tagged after pull)
- hermes3 (already have, include for completeness)

## LiteLLM aliases

Add these to `~/Projects/ai-stack/litellm/litellm-config.yaml` (or whatever the actual config path is):

```yaml
model_list:
  # ... existing aliases ...
  
  - model_name: cerebra-classifier-qwen35-9b
    litellm_params:
      model: ollama/qwen3.5:latest
      api_base: http://ollama:11434
  
  - model_name: cerebra-classifier-qwen35-4b
    litellm_params:
      model: ollama/qwen3.5:4b
      api_base: http://ollama:11434
  
  - model_name: cerebra-classifier-llama31-8b
    litellm_params:
      model: ollama/llama3.1:8b
      api_base: http://ollama:11434
  
  - model_name: cerebra-classifier-olmo3-7b
    litellm_params:
      model: ollama/olmo-3:7b
      api_base: http://ollama:11434
  
  - model_name: cerebra-classifier-granite4-tiny
    litellm_params:
      model: ollama/ibm/granite4:tiny-h
      api_base: http://ollama:11434
  
  - model_name: cerebra-classifier-granite4-micro
    litellm_params:
      model: ollama/ibm/granite4:micro
      api_base: http://ollama:11434
  
  - model_name: cerebra-classifier-smollm3
    litellm_params:
      model: ollama/<smollm3-tag-after-pull>  # use exact tag from `ollama list`
      api_base: http://ollama:11434
  
  - model_name: cerebra-classifier-hermes3
    litellm_params:
      model: ollama/hermes3
      api_base: http://ollama:11434
```

Restart the LiteLLM container after editing the config.

## Test approach

**Use the v0.1.0 two-pass classifier with the v0.1.0 prompts (PROMPT_VERSION 2.0.0).** Don't tune the prompts per model — that's a different experiment. The point is to isolate the model-substrate effect with everything else held constant.

**Settings constant across all runs:**
- Temperature: 0.0
- think: false (where supported — this is critical for Qwen 3.5 and SmolLM3)
- Same fixture set (30 fixtures with the 4 ambiguous markings)
- Same scoring (0.5-credit on ambiguous_with matches)
- Same two-pass architecture
- Three runs per model (variance signal)

**Per model, capture:**
1. Strict accuracy (X/30)
2. Partial-credit accuracy (X.5/30)
3. Clear-case accuracy (X/13)
4. Ambiguous-case accuracy with credit breakdown (X/2)
5. Hard-case accuracy (X/15)
6. 4-quadrant table (high/low confidence × correct/wrong)
7. Per-call latency: min, max, mean, p50, p95
8. Pass 1 quadrant accuracy
9. Pass 2 within-quadrant accuracy (conditional on Pass 1 correct)
10. JSON parse failure rate (if any)
11. Run-to-run variance (3 runs same model, same fixtures, do they agree?)
12. Per-category accuracy (which D1 categories does this model handle well/badly?)
13. Total VRAM used during inference (from `nvidia-smi` snapshot mid-run)

## Implementation

This is a temporary test harness, not production code. Acceptable to write it as a standalone script that's not committed (or committed under `scripts/experimental/multi_model_calibration.py` with a clear "not production" note).

Suggested structure:

```python
# scripts/experimental/multi_model_calibration.py
"""
Run v0.1.0 two-pass calibration against multiple model backends.
Produces a comparison table to inform Phase 2 production model choice
and v0.2 LoRA training target.

NOT PRODUCTION CODE. Experimental harness.
"""

MODELS_TO_TEST = [
    "cerebra-classifier-qwen35-9b",
    "cerebra-classifier-qwen35-4b",
    "cerebra-classifier-llama31-8b",
    "cerebra-classifier-olmo3-7b",
    "cerebra-classifier-granite4-tiny",
    "cerebra-classifier-granite4-micro",
    "cerebra-classifier-smollm3",
    "cerebra-classifier-hermes3",
]

NUM_RUNS_PER_MODEL = 3

def run_calibration_for_model(model_alias: str, run_num: int) -> dict:
    """Run the v0.1.0 two-pass calibration against one model, capture all metrics."""
    # Instantiate classifier with this model alias
    # Run calibration test
    # Capture all 13 metrics from the test plan
    # Return as dict
    ...

def main():
    results = {}  # {model_alias: [run1_dict, run2_dict, run3_dict]}
    
    for model in MODELS_TO_TEST:
        results[model] = []
        for run_num in range(NUM_RUNS_PER_MODEL):
            print(f"Running {model}, run {run_num + 1}/{NUM_RUNS_PER_MODEL}")
            results[model].append(run_calibration_for_model(model, run_num))
    
    # Produce comparison output
    write_comparison_table(results, "multi_model_comparison.md")
    write_raw_results(results, "multi_model_comparison_raw.json")

if __name__ == "__main__":
    main()
```

## Output format

Produce `docs/agent/multi_model_comparison.md` with:

### 1. Summary table

| Model | Size | Mean Partial Acc | Std Dev (3 runs) | Mean Latency | VRAM |
|-------|------|------------------|------------------|--------------|------|
| qwen3.5-9b | 9.7B | X% | ±Y% | Z s | N GB |
| qwen3.5-4b | 4B | ... | ... | ... | ... |
| llama3.1-8b | 8B | ... | ... | ... | ... |
| olmo-3-7b | 7B | ... | ... | ... | ... |
| granite4-tiny | ~7B MoE | ... | ... | ... | ... |
| granite4-micro | 3B | ... | ... | ... | ... |
| smollm3 | 3B | ... | ... | ... | ... |
| hermes3 | 8B | ... | ... | ... | ... |

### 2. Per-model detail sections

For each model:
- Full 4-quadrant table
- Per-category accuracy (which D1s does it handle well?)
- Run-to-run variance details
- JSON parse failures (if any)
- Any anomalies (timeouts, malformed outputs, infinite loops)
- Subjective notes ("model frequently refused to commit to a category" / "model produced very confident outputs even when wrong" / etc.)

### 3. Strict vs partial accuracy comparison

Show whether the gap (strict vs partial-credit) is consistent across models or whether some models specifically benefit from ambiguous-case credit more than others. This is signal about how each model handles boundary cases.

### 4. Cross-model agreement analysis

For each fixture, how many models got it right? Which fixtures did all models get right (consensus correct), which did most models miss (consensus failure), which did models split on (ambiguous in practice)?

This is genuinely diagnostic data — fixtures where every model fails are either bad fixtures or fundamentally hard chunks. Fixtures where models split predict that counsel-mode would help.

### 5. Recommendation section

Based on the data, recommend:

**For Phase 2 production model:**
The model that scored highest on partial-credit accuracy, with reasonable latency. If there's a tie, prefer:
- Smaller model (faster iteration, less VRAM)
- Lower run-to-run variance (more reproducible)
- Lower hallucination signature (low strict-vs-partial gap = good calibration)

**For v0.2 LoRA training target:**
The model that scored well AND has documented training methodology AND fits comfortably in 12GB VRAM for QLoRA training. OLMo 3 7B is the strong candidate per available documentation; verify it performed adequately on the comparison.

If different models win each category, that's fine — Phase 2 ships on one model, v0.2 LoRA targets another.

### 6. Raw data

Attach `multi_model_comparison_raw.json` with full per-fixture predictions and metrics for every run. This is the corpus for any future analysis.

## Estimated runtime

- 8 models × 3 runs × ~30 chunks × ~5-15s per chunk = 1.5-4 hours total compute
- Plus warmup/cooldown between models
- Plus comparison analysis writing time

Realistic: half a day of mostly-unattended runs with intermittent checking.

## Anomalies to watch for

**Model refuses to commit**: Some models, especially smaller ones, will say "I can't determine this" or output null. Count these as JSON parse failures and report frequency. Don't try to retry — the refusal IS the signal.

**Thinking mode leaks through**: Even with think: false explicitly set, some models may still produce reasoning chains before output. Watch latency — if it varies wildly call to call, thinking is probably leaking. Document where this happens.

**OOM during model loading**: Granite4-tiny and OLMo-3-7b are at the edge of what's comfortable with other models loaded. May need to `ollama stop <model>` between tests to free VRAM. The test script should handle this gracefully.

**Different JSON schemas**: Some models may produce slightly different JSON shapes (extra fields, missing fields, different key names). The classifier code should be defensive about parsing; document parse-failure rate per model.

**Variance higher than expected**: At temperature 0.0 there should be near-zero variance between runs. If you see >5% variance, something nondeterministic is leaking. Document and flag — this means we have a reproducibility problem we didn't know about.

## What this is NOT

This is not a benchmark for "which is the best model overall." It's specifically about Cerebra's SKU classification task. A model that scores poorly here might be excellent at other tasks.

This is also not a commitment to any model. The results inform decisions but don't make them. After this completes, we discuss the recommendations and choose.

## Don't list

- Do NOT modify the v0.1.0 prompts to "tune" them for specific models
- Do NOT modify the fixture set during this comparison
- Do NOT iterate on prompt structure during the comparison
- Do NOT add models not in the list above without checking first
- Do NOT change the v0.1.0 production model based on these results without explicit decision approval

## Final note

If most/all models score in the 50-65% range, that's not a sign of poor model quality — it's strong evidence that the 16-category taxonomy genuinely requires fine-tuning to handle, not just better prompts. That would itself be useful data for v0.2 planning.

If one model scores significantly higher (say, 75%+), that's important signal worth understanding — what about that model fits Cerebra's task better?

If results are wildly variable across runs of the same model at temperature 0.0, that's a determinism problem we need to investigate before relying on any model in production.

Report findings. We'll decide next steps from the data.
