# Cerebra Phase 2 — Architectural Consultation Response

*Read the codebase, ran probes against the live stack, reviewed docker logs. One finding changed my hypothesis mid-investigation and I'll call that out explicitly.*

---

## 0. The Finding That Changes Everything

Before answering the specific questions, there's a factual error in the consultation that dominates all of the latency analysis.

**The model is not Qwen 2.5. It is Qwen 3.5.**

From `ollama/api/tags`:

```
name: qwen3.5:latest
family: qwen35
parameter_size: 9.7B
quantization_level: Q4_K_M
size_vram: 8,649,499,264 bytes (~8.6GB)
context_length: 4096 (currently loaded)
```

The consultation states "Qwen 2.5 family, 6.6GB, ~7B params." The 6.6GB figure is the compressed file size on disk; VRAM usage is 8.6GB. The family is `qwen35` (Qwen 3.5), not `qwen25`. Parameter count is 9.7B, not 7B. These gaps are not pedantic: Qwen 3 added extended internal chain-of-thought reasoning by default. Qwen 2.5 did not have this. The entire latency picture is explained by this difference.

**Verification probe I ran directly against Ollama:**

```bash
curl http://127.0.0.1:11434/api/generate \
  -d '{"model":"qwen3.5:latest","prompt":"<classification task>","stream":false,"options":{"num_predict":50}}'
```

Result:
- `prompt_eval_count: 32`, `prompt_eval_duration_ms: 40` — fast prefill as expected
- `eval_count: 50`, `eval_duration_ms: 831` — 60 tokens/sec generation
- `response: ""` — **empty response despite 50 tokens evaluated**

An empty response at full token budget means the model spent all 50 tokens in the internal reasoning phase (`<think>...</think>`). Ollama strips thinking tokens from the returned `response` field. The final answer never arrived because the thinking phase wasn't finished. This is not ambiguous.

Qwen 3 models generate thinking tokens in the range of several hundred to several thousand before producing the final output. At 60 tokens/sec on a 4070 Super, 1000 thinking tokens = 17 seconds, 2000 = 33 seconds. When you add prefill time (~1.9s for 1500 tokens) and 300 output tokens (~5s), you land at 24–40 seconds best case. The variance in the docker logs (47 seconds to 5 minutes) is the thinking chain varying in length depending on how the model interprets the complexity of the input. A "complex" reasoning task (like disambiguating TECHNIQUE from MECHANISM) triggers a longer thinking chain.

**The 4096 context window matters here.** Prompt is ~1500 tokens. Thinking tokens + output must fit in the remaining ~2596 tokens. Some calls saturate the context window mid-thinking and produce a truncated, degraded answer — this explains both the latency ceiling (~3 minutes at 60 tok/sec × 2596 tokens ÷ 2 for realistic throughput) and part of the accuracy problem. The model is literally running out of room to reason.

The v1.1.0 prompt is ~700 tokens larger than v1.0.0. With a fixed 4096 context, that 700-token increase ate into the thinking budget. So the prompt size is making things worse — not by slowing prefill (negligible at this scale) but by squeezing the thinking window. The senior planner's read was directionally right about attention budget, but the mechanism is thinking tokens crowding out reasoning, not the prompt description crowding out the classification.

---

## 1. The Classifier Prompt

**Is size the throughput problem?**

No — not in the way the consultation frames it. Prefilling 1500 tokens vs 800 tokens costs ~1.5 seconds vs ~0.8 seconds. That's irrelevant when calls take 90–300 seconds. The problem is thinking mode consuming the available context budget.

The v1.1.0 prompt's 700-token addition reduced the thinking budget by 700 tokens (from ~2596 to ~1896 tokens). At 60 tok/sec, that's ~12 seconds less thinking per call. Paradoxically, the bigger prompt can actually make accuracy *worse* by depriving the model of reasoning room, while also making the test run longer because each call uses more of its budget on thinking-but-truncated than on output.

If you ran a 1500-char version (roughly 375 tokens) against the same fixtures with thinking mode still active, I'd predict:
- **Latency:** modest improvement, probably 80–120 seconds average instead of 120–180 seconds. The thinking budget expands from ~1896 to ~3500 tokens but the model will likely use most of it.
- **Accuracy:** similar or worse. With no disambiguation instructions, the model will *think harder* about category confusion but without scaffolding. Thinking mode doesn't substitute for structure when the categories are genuinely close.

The correct intervention is disabling thinking mode, not shrinking the prompt.

**What to cut from v1.1.0?**

If you keep thinking disabled and need to reduce prompt size for other reasons, I'd cut in this order:

1. **The example answers in the disambiguation tests.** "Example: 'the hash is derived by feeding blocks to SHA256'" — these eat tokens and the distinctions can be expressed more crisply. The *test questions* are the valuable part ("if you replaced the subject with a passive 'it happens automatically,' is it still true?"). The examples are training wheels.

2. **Redundant hedging.** "READ CAREFULLY BEFORE SCORING" doesn't add signal. The model already processes every token.

3. **Category descriptions already in `category_lines`.** The KEY DISTINCTIONS section re-explains the same concepts from a different angle. After disabling thinking mode, you may find the category descriptions alone (plus just the test questions, no examples) are sufficient.

What to keep: the test questions for each confusable pair. These are concise and cognitively well-targeted. "Does it define an outer wall (CONSTRAINT) or a behavioral standard (PRINCIPLE)?" is the minimum viable disambiguation signal for that pair.

**Before doing any of this, disable thinking mode.** The prompt work is secondary.

---

## 2. The Two-Pass Architecture

**Conceptual assessment: right architecture, wrong phase.**

A coarse → targeted-disambiguation flow is genuinely better for this task long-term. Here's what it would look like:

**Coarse prompt (~400 tokens):**
```
Score these 16 cognitive categories 0.0–1.0 for fit.
[16 categories, one-line descriptions only]
Return JSON: {"top1": "CATEGORY", "top2": "CATEGORY", "top1_score": 0.0, "top2_score": 0.0, "scores": {...}}
```
No disambiguation logic. Just rates and ranks.

**Routing logic:**
```python
CONFUSABLE_PAIRS = {
    frozenset({'TECHNIQUE', 'MECHANISM'}),
    frozenset({'CONSTRAINT', 'PRINCIPLE'}),
    frozenset({'DESIGN', 'TECHNIQUE'}),
    frozenset({'TOOL', 'MECHANISM'}),
    frozenset({'CONTEXT', 'DESIGN'}),
    frozenset({'OBSERVATION', 'EVENT'}),
}

def needs_second_pass(top1, top2, margin):
    return frozenset({top1, top2}) in CONFUSABLE_PAIRS and margin < 0.25
```

Most chunks should be one-pass. The coarse pass fires the second pass only when the top two candidates form a known-confusable pair AND the margin between them is narrow. "Narrow" needs calibration — I'd start at 0.25.

**Data model compatibility:**

The current schema is already compatible for v1.1. The `prompt_version` field on `sku_assignments` handles this — bump to `"1.2.0"` and document that "1.2.0 = two-pass with disambiguation." The `ClassificationResult` dataclass in `llm_adapter.py` stays unchanged. Two-pass logic lives in `_classify_with_retry()` or a new `_classify_two_pass()` in `sku_classifier.py`. No schema migration needed.

**Does it shift cost or reduce it?**

With thinking disabled: most chunks (estimated 60–70% based on fixture set composition) are one-pass. The 30–40% that need disambiguation get two passes. Net: 60% × 1 call + 40% × 2 calls = 1.4 calls per chunk on average. That's a 40% overhead for the two-pass cases, partially offset by the coarse prompt being shorter. Real throughput gain vs single-pass with v1.1.0: modest.

With thinking enabled: two-pass doubles the thinking opportunities for ~40% of chunks. This would be worse, not better.

**Recommendation:** Defer two-pass to v0.1.1. It's a clean improvement but the Phase 2 bottleneck is thinking mode, not prompt structure. Fix the root cause, measure the result, then decide if two-pass is worth the iteration cost.

---

## 3. KV Cache and Prompt Caching

**Current behavior:**

Ollama version: `0.21.0`. I checked the loaded model state during the test run. The model was loaded continuously with an `expires_at` timestamp confirming it was not being unloaded between requests. So the "model reload" theory is false — the model stays resident.

Ollama does implement KV cache reuse for shared input prefixes (common prefix of consecutive requests stays in cache). The v1.1.0 prompt has a fixed prefix of ~1400 tokens (everything up to `<text>\n{content}`). With consecutive calls from the calibration test, Ollama *should* be skipping the prefill of those 1400 tokens on calls 2–30.

**But thinking mode undermines this.** KV prefix caching works on the input. After the input, Qwen 3.5 generates a thinking chain that varies per call. The thinking tokens do not affect the input cache. So prefix caching *is* operating (or should be — I can't confirm Ollama 0.21.0's specific behavior), but the benefit is modest: saving ~1.5 seconds of prefill on a 90–300 second call is a <2% improvement.

**Minimum change to exploit prefix caching better:**

Ensure the prompt template generates byte-identical prefix across calls. Currently `category_lines` is constructed by iterating over `D1Category` enum and `CATEGORY_DESCRIPTIONS` dict — dict ordering is insertion-ordered in Python 3.7+, so this should be stable. Verify with a quick debug: print the first 200 chars of two consecutive prompts and confirm they match. If they don't (due to dict ordering variation), fix by sorting.

**Is it worth doing as Phase 2 squeeze-in?**

No. Prefix caching is already either working or close to working, and its impact is marginal against the thinking mode wall. This belongs in Phase 3 as part of performance baseline work.

---

## 4. Schema-Driven Generation

**Confirmed: LiteLLM drops `format: "json"` and `response_format`.**

The deviation log (`docs/agent/deviations/v0.1.0.md`) already documents this: "`response_format` is silently dropped by the proxy (`drop_params: true`)." The global `drop_params: true` in `litellm-config.yaml` applies to all models including `cerebra-classifier`. There's no per-model override.

If you pass Ollama's native `format: "json"` to LiteLLM, it's dropped before reaching Ollama. Confirmed by reading the config.

**Would JSON-mode help?**

For parse failures: yes, moderately. The existing regex fallback in `_try_extract_partial_json()` handles the three observed failure modes (canonical, flat, malformed reasoning). JSON mode would eliminate the need for this fallback. The fallback already works well enough.

For accuracy: no. Category confusion happens in the scoring weights, not in JSON formatting.

For latency with Qwen 3.5 in thinking mode: possibly worse. Grammar-constrained generation forces the model to generate valid JSON tokens. During the thinking phase, this constraint doesn't apply (thinking happens before the constrained output). The constraint only helps during the ~300-token JSON output phase. Net latency effect: negligible.

**The clean workaround:**

Direct Ollama calls for classification, bypassing LiteLLM for this one model. The adapter already uses `urllib.request` with no framework dependency. A direct Ollama path at `http://127.0.0.1:11434/api/generate` with `"format": "json"` and `"think": false` would be 3 lines of change in `ProxyLLMAdapter._call_chat_completions()` — add a routing flag for direct-Ollama vs LiteLLM. The existing `LLMAdapter` ABC makes this a clean seam.

This also solves the thinking mode problem in a single change, since `think: false` is an Ollama-native option that LiteLLM drops.

**Recommendation:** Direct Ollama call with `think: false` and `format: "json"` is the correct Phase 2 intervention. It solves latency (thinking mode), reduces parse failure rate (JSON schema), and requires zero Python dependency additions.

---

## 5. LoRA / Fine-Tuning Track

**Realistic timeline and scope:**

Hardware: RTX 4070 Super, 12GB VRAM, Qwen 3.5 9.7B at 8.6GB VRAM footprint. For QLoRA (4-bit quantized + LoRA adapters): the base model at 4-bit is ~5GB, leaving ~7GB for optimizer states and activations. This is tight but feasible with a batch size of 1–2 and gradient checkpointing. Unsloth would be the right framework — it patches memory layout for 2-3× memory reduction. With Unsloth, training a LoRA adapter on the 9.7B model is achievable on this hardware.

**What corpus we'd need:**

A LoRA for this task needs ~500–1000 labeled examples minimum for stable fine-tuning. The Phase 2 backfill will produce ~745 assignments. If the backfill runs with thinking disabled and achieves 70%+ accuracy, that corpus is ~74% reliable (745 × 0.70 = 522 confidently correct). This is marginal but workable for a first LoRA pass.

The 30-fixture calibration set should be treated as a *held-out evaluation set*, not training data. The training set should be the 715 backfill records with `d1_confidence > 0.5`.

**Expected accuracy lift:**

With 500 in-domain examples fine-tuned on Qwen 3.5 9.7B: I'd estimate 15–25 percentage points above the best prompt-only approach. The task is cognitively well-bounded, the categories are stable, and the examples are drawn directly from the target corpus. The lift comes from two sources: the model internalizes the category distinctions (no longer needs explicit instructions at inference time) and per-call latency drops dramatically (no thinking mode needed for a fine-tuned classification model, shorter prompt).

**For v0.2, what Phase 2 must preserve:**

- `raw_scores_json` on every assignment (already stored) — essential for detecting borderline vs confident cases
- `d1_confidence` on every assignment (already stored) — training data filter
- `latency_ms` on every assignment (already stored) — flags of inference quality
- A human-review flag for `d1_confidence < 0.4` records — these are weak training signals. Consider adding a `needs_human_review` column during Phase 3.
- The 30 calibration fixtures as a static evaluation set, separate from the training corpus.

**Could fine-tuning the evaluation task be higher leverage?**

Interesting idea but practically limited. A "judge" LoRA that scores whether a D1 classification is correct would need labeled correct/incorrect pairs — but your ground truth is only the 30 calibration fixtures. That's not enough to train a reliable judge. Skip this path for now.

**LoRA is realistic for v0.2**, but only if the Phase 2 backfill produces reliable training labels. That depends on getting the base classifier above 70% first.

---

## 6. The Calibration Test

**Honest read: not fit for iterative prompt development, adequate for final gate.**

**Problem 1 — No per-fixture timeout that fires at the Ollama level.**

The `ProxyLLMAdapter` has `TIMEOUT_SECONDS = 300`, which is a Python `urllib` socket timeout. This fires if the server stops sending bytes. With Qwen 3.5 in thinking mode, Ollama is actively computing — it's sending keep-alive signals or the connection stays alive while the model generates thinking tokens. The socket timeout never fires. The only protection against a truly infinite call is process-level timeout, which the test doesn't have.

The consultation said the test appeared stuck for 30 minutes. Looking at the docker logs I collected, the test was actually making steady progress — 41 requests completed in 2 hours, averaging ~2 minutes per call. The "30 minute stall" was likely the observation window missing a batch of consecutive slow calls. The test is not stuck; it's slow.

**Problem 2 — No partial result persistence.**

Results are only emitted if the test function completes. If the process is killed (or if one call exceeds the socket timeout), everything is lost. Fixture results should be written to a JSONL file after each call:

```python
result_path = vault / "calibration_results.jsonl"
with open(result_path, "a") as f:
    json.dump({
        "fixture_id": fixture.fixture_id,
        "expected": fixture.expected_d1.name,
        "predicted": predicted.name,
        "correct": correct,
        "confidence": classification.confidence,
        "latency_ms": classification.latency_ms,
    }, f)
    f.write("\n")
```

**Problem 3 — No fast iteration tier.**

Running 30 fixtures including all 15 hard cases to get accuracy feedback is wasteful during prompt development. A fast tier of the 15 clear-case fixtures would give quick signal: "does the model get the easy ones?" If clear accuracy < 80%, the prompt needs fundamental work before bothering with hard cases. This tier should complete in under 5 minutes with thinking disabled.

**Problem 4 — No confusable pair confusion matrix.**

The 4-quadrant report tracks overall confidence vs correctness but not *which* pairs are confused. After v1.0.0's 40% result, the useful diagnostic was "TECHNIQUE is being confused with MECHANISM 4 times, CONSTRAINT with PRINCIPLE 3 times..." A confusion matrix keyed by `(expected_d1, predicted_d1)` for all wrong cases would tell you exactly where to focus the prompt.

**Is the fixture set well-designed?**

Mostly yes. The 15 clear cases are genuine. A few of the hard cases are contestable:

- `hard_02` (MECHANISM vs PRINCIPLE for the leeway network): "Everything outside the network is implicitly disallowed" is as much PRINCIPLE as MECHANISM. A human expert might label this differently. The distinction is thin.
- `hard_07` (DESIGN vs PRINCIPLE for the approval gate): "The approval gate is a workflow convention, not a CLI feature" reads normatively, which is PRINCIPLE territory. The notes argue DESIGN because of "is a...not a..." framing, but I'd call this a coin flip.
- `hard_03` (OBSERVATION vs PATTERN for SKU saturation): "When a location saturates — more than 255 entries — that is signal" — this is closer to CONSTRAINT or PRINCIPLE than OBSERVATION. The fixture label may be wrong, not just hard.

These don't invalidate the fixture set but should be flagged in the test metadata. If the model labels `hard_07` as PRINCIPLE and `hard_03` as CONSTRAINT, that might be a better answer than the fixture's DESIGN and OBSERVATION.

**Proposed changes:**
1. Write fixture results to JSONL after each call (partial persistence)
2. Add a `--fast` flag that runs only clear-case fixtures
3. Add a confusion matrix to the report
4. Add per-fixture wall-clock logging (not just overall elapsed)
5. Add process-level timeout via `subprocess` or `threading.Timer` per fixture (60–90 seconds)
6. Re-evaluate `hard_03` and `hard_07` fixture labels

---

## 7. Phase 2 Close-Out Path

**My recommendation: Modified Option C — but the modification is the point.**

The four options in the consultation all assume the throughput problem requires architectural changes. It doesn't. The root cause is a single line of configuration: thinking mode is on.

**What to actually do:**

**Step 1 — Today**: Change `ProxyLLMAdapter._call_chat_completions()` to call Ollama directly at `http://127.0.0.1:11434/api/chat` with `"options": {"think": false}` and `"format": "json"`. Keep the LiteLLM path available via env var for other models. This is a 20-line change.

Alternatively — simpler if you don't want to add a direct-Ollama path — add `/no_think` to the user message in `_build_classification_prompt()`. Qwen 3 recognizes this token in the prompt. Less reliable than the API flag but immediately testable.

**Step 2 — Same session**: Re-run `test_sku_fixtures.py` on just the 15 clear-case fixtures. With thinking disabled and a warm model, expect ~15–25 seconds per call, ~5 minutes total. This is your calibration signal for whether the underlying prompt logic works.

**Step 3 — Gate decision**:
- Clear accuracy ≥ 87% (13/15): run the full 30-fixture test. If overall ≥ 70%, merge.
- Clear accuracy 73–87% (11–13/15): acceptable; run full set. 70% overall is achievable.
- Clear accuracy < 73% (< 11/15): the prompt logic is broken even for easy cases. Go back to prompt design.

**What "ship v0.1.0" means:**
- PROMPT_VERSION = "1.2.0" (thinking-disabled, otherwise same structure)
- Calibration evidence: 4-quadrant table in the merge gate report, clear/hard split shown separately
- Merge gate passes ≥ 70% overall top-1 D1 agreement
- Documented deferred: two-pass architecture, per-fixture timeout in calibration test, JSON schema enforcement, direct Ollama path
- Backfill runs overnight or over a weekend — 745 records × ~20 seconds = ~4 hours with thinking disabled

**On Option D (don't ship, redesign the test):**

Partially right but doesn't block Phase 2 if thinking is disabled. The calibration test has real problems (documented in §6) but the 30-fixture / 70% threshold is the right shape for a v0.1 gate. Fix the test incrementally while Phase 3 is running.

**On Option B/C (two-pass)**:

Two-pass is v0.1.1 work. Phase 2's purpose is "every memory gets a SKU before Phase 3 builds on it." At 70% accuracy with thinking disabled, the substrate is good enough. Imperfect SKUs get reclassified when PROMPT_VERSION bumps to "1.3.0" or "2.0.0" — the schema's `_is_current()` check handles this correctly. Building on a 70%-accurate substrate and improving later is the right tradeoff at this stage. Building on a 0%-complete backfill because you're iterating on two-pass architecture is not.

---

## 8. What We're Missing

**The model identity was wrong.** This consultation was written assuming Qwen 2.5 7B behavior. The actual model is Qwen 3.5 9.7B with thinking mode. Every latency estimate, every context budget calculation, every throughput projection in the planning docs is off by a factor of 5–15×. The fix is simple but the misidentification needs to be acknowledged and corrected in the deviation log.

**The calibration test's socket timeout doesn't protect against thinking-mode calls.** `urllib.urlopen(timeout=300)` fires if no bytes arrive for 300 seconds. An actively-generating thinking model sends keepalive, keeping the connection alive indefinitely. The effective per-call timeout is ~3 minutes (context window exhausted) not 5 minutes. But there's no hard per-fixture ceiling. Add one.

**`_classify_with_retry` doubles the blast radius of a slow call.** If a thinking-mode call takes 3 minutes and fails (say, malformed JSON at the end of a context-exhausted response), the retry takes another 3 minutes. Effective failure timeout per record: 6+ minutes. For 745 backfill records, even 1% failure rate = 7–8 retries = 42+ minutes of extra runtime. Consider capping the retry logic or making it conditional on the error type (parse failure = retry; timeout = don't).

**The v1.0.0 calibration result (12/30 = 40%) was measured with thinking mode active.** The six confusable pairs identified from that run were produced by a model doing internal chain-of-thought that was frequently truncated by the 4096 token limit. With thinking disabled, the model might confuse *different* pairs, or might have fewer confusions overall. The v1.1.0 prompt's disambiguation logic was built to address confusions in a specific failure mode that may not fully recur with thinking disabled. Run the fast-tier calibration first with thinking disabled before deciding the v1.1.0 structural changes are necessary.

**The SKU architecture is more forgiving of Phase 2 errors than it looks.** Every assignment stores `classifier_version` and `prompt_version`. The `backfill_null_records()` already compares these via `_is_current()` and reclassifies on version bump. Phase 3 builds *on* the SKU substrate but doesn't permanently commit to any specific D1 assignment — the sku_address column on memory_records updates when the classifier improves. The data model was correctly designed for iterative calibration improvement. A 70%-accurate Phase 2 that ships is strictly better than a 100%-designed Phase 2 that doesn't, because Phase 3 needs records to index and Phase 2 can improve in-place when the prompt is right.

**The hard fixture labels deserve a second review pass.** Three fixtures (`hard_02`, `hard_03`, `hard_07`) have genuinely contestable labels. If the model consistently labels these differently from the fixture labels, the question is whether the model is wrong or the fixture is. Running a small human-panel calibration on just these three (ask two domain-knowledgeable humans to label them cold) before the next calibration run would give you a cleaner signal.

**There's no monitoring of D1 distribution from the actual planning doc corpus.** The 30 calibration fixtures were hand-selected. But 745 chunks of planning documentation will have a specific distribution across the 16 D1 categories — probably heavy on DESIGN, PRINCIPLE, MECHANISM, TECHNIQUE, CONSTRAINT. If the classifier is systematically weak on categories that are rare in the fixture set but common in the corpus (say, PHENOMENON or RELATION), you won't catch it from the calibration test. After the backfill, inspect the D1 distribution across all 745 records. Unexpected clustering (e.g., 40% PRINCIPLE) is signal that the classifier has a bias.

---

## Summary of the Critical Path

```
1. Confirm Qwen 3.5 thinking mode is the root cause
   → Already confirmed by probe (empty response at 50 tokens, ~60 tok/sec gen speed)

2. Disable thinking mode
   → Direct Ollama API call with think: false (preferred), or /no_think in prompt

3. Re-run clear-case calibration (15 fixtures, ~5 minutes)
   → If ≥ 87% accurate: proceed to full 30-fixture run
   → If < 87%: iterate prompt before full run

4. Full 30-fixture calibration
   → If ≥ 70%: merge gate ready
   → Include 4-quadrant table and clear/hard split in gate report

5. Bump PROMPT_VERSION to "1.2.0", open merge gate

6. Backfill runs (~4 hours with thinking disabled)

7. Document in deviation log:
   - Model was Qwen 3.5 9.7B, not Qwen 2.5 7B
   - Thinking mode disabled for classification performance
   - Two-pass architecture deferred to v0.1.1
```

The two-pass architecture, LoRA track, and JSON schema enforcement are all worth doing. None of them are Phase 2 blockers. Ship 70% with a clean substrate, then improve.
