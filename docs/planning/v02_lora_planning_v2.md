# Cerebra v0.2 — LoRA Training for SKU Classifier

*Drafted 2026-06-06. v2 revision integrates feedback on curation approach, evaluation philosophy, validation cadence, and execution sequencing.*

## What this doc is

The design plan for v0.2 Cerebra work: LoRA fine-tuning the SKU classifier on Phase 2's backfill corpus to lift classification quality from v0.1.0's 65% partial-credit accuracy to a meaningfully higher target. This is the bridge from "we have a substrate" to "we have a fine-tuned classifier whose representations include the 16-category taxonomy."

This is *not* a tutorial on LoRA training, *not* a complete v0.5+ roadmap, and *not* a checklist for execution. It's the design decisions made with rationale, written down so implementation has a clear target.

## Goal and success criteria

**Primary goal:** Lift the SKU classifier's partial-credit accuracy from 65% (v0.1.0 production baseline) to 85%+ on a held-out evaluation set that does NOT overlap with training data.

**Secondary goals:**

1. **Improved confidence calibration.** v0.1.0's Granite 4.1 3B already shows honest confidence behavior (low confidence on short/ambiguous inputs). v0.2 should preserve or improve this — high confidence should correlate with high accuracy.
2. **Reduced PRINCIPLE bias.** The training corpus is 30% PRINCIPLE; without class balancing this gets reinforced. v0.2 should show roughly equal accuracy across categories, not skewed toward over-represented classes.
3. **Maintained determinism.** Same chunk → same SKU at temperature 0.0, just like v0.1.0.
4. **Per-pair improvement on known confusables.** The 6 categorical boundaries identified in earlier calibration (TECHNIQUE↔MECHANISM, CONSTRAINT↔PRINCIPLE, DESIGN↔TECHNIQUE, TOOL↔MECHANISM, CONTEXT↔DESIGN, OBSERVATION↔EVENT) should show measurable improvement.

**Stretch goal:** Reach 90%+ partial-credit accuracy. This would put Cerebra's classifier at a quality level where Phase 3+ retrieval can rely on SKUs as a primary signal rather than one signal among several.

**Failure criteria (when we stop and reconsider):**

- LoRA-tuned model scores worse than v0.1.0 baseline on the held-out evaluation set
- LoRA training doesn't converge (loss plateaus high or oscillates)
- Determinism breaks
- VRAM or latency in production becomes unacceptable
- Per-category accuracy becomes more skewed, not less

## On test validity — the philosophical foundation

Before any training, an honest acknowledgment: we don't fully know whether our tests measure what we want them to measure.

The 30 calibration fixtures are hand-labeled approximations of "correct classification." Two audits have already revised those labels when the data made it clear they were imperfect. More revisions are likely as v0.2+ work surfaces blind spots the current test design can't see.

This isn't a flaw to be fixed before training — it's a structural property of evaluation. Any test is a partial lens. The honest approach isn't to demand a perfect test before proceeding; it's to triangulate across multiple imperfect lenses and watch for places they disagree.

The principles we work under:

**Trust no single test.** When a single test says "this is good," we look at additional surfaces (other tests, production behavior, manual spot-checks) before believing it. When multiple surfaces agree, confidence rises.

**Treat divergence between test and reality as test signal.** If automated evaluation says the LoRA is great but spot-checking shows weird outputs, the test has a blind spot. Update the test, not just the model.

**Iterate the test design alongside the model design.** v0.2 evaluation will improve on v0.1.0's. v0.3 will improve on v0.2's. The test is never finished; it matures as our understanding does.

**Manual spot-checks catch what automated metrics miss.** Numbers can show improvement that's actually skew or overfitting. Reading 20 actual model outputs against actual chunk content catches systematic problems no aggregate metric will surface.

This shapes the evaluation strategy. We don't have one yardstick; we have several. We watch for the cases where they disagree.

## Training corpus construction

This is the most decision-heavy section. The 745-record backfill is raw material — what we feed to LoRA is what we construct from it.

### The honest problem

The v0.1.0 backfill labels are produced by a model that scores 65% partial accuracy on calibration. That means roughly 35% of the backfill labels are either wrong or contestable. Training on those teaches the LoRA to reproduce the errors, not correct them.

We have a quality commitment, so this can't be hand-waved. The training corpus needs to be more reliable than the backfill that produced it.

### Curation strategy — three stages

**Stage 1 — Confidence filtering.**

Use the model's Pass 2 confidence score as a quality signal. Initial threshold guess: keep assignments where Pass 2 confidence ≥ 0.70.

The actual threshold gets determined empirically:

1. Pull the confidence scores from all 745 backfill assignments
2. Bucket them (≥0.9, 0.8-0.9, 0.7-0.8, 0.6-0.7, <0.6)
3. Pick a threshold based on the actual distribution

If the distribution is bimodal (cleanly separates high-confidence from low), the threshold is obvious. If smooth, we make a judgment call at the cut point that preserves most genuine quality.

Expected impact: ~80-85% of records pass (~595-635 examples).

**Stage 2 — Cross-model consensus filtering.**

For chunks that passed Stage 1, run them through 2-3 other models (e.g., Qwen 3.5 9B, Llama 3.1 8B, Granite 4.0 Micro) using the same v2.0.0 prompts. If at least 2 of 3 models agree with the v0.1.0 backfill label, the example is high-consensus. If models disagree, the example is contested.

Why this works: cross-model agreement is empirically a stronger signal than single-model confidence. Round 1 and Round 2 calibration data demonstrated this — the 5 consensus-failure fixtures turned out to be label problems, not model failures.

Expected impact: of the ~600 confidence-filtered records, maybe 400-500 are high-consensus, and 100-200 are contested.

**Stage 3 — Comprehensive manual review.**

The user is committing to do a full manual pass through the corpus, not just spot-check the contested cases. This is more work but more thorough.

Process:

1. User reads each retained training example (chunk content + assigned label + model alternatives if available)
2. For each, makes a verdict: keep / relabel / mark ambiguous / drop
3. Where unsure, flags for review with me — we calibrate the edge cases together
4. Results go back into a curated training set

The cost: significant time investment (~2-4 hours of focused review for ~700 records at ~15-20 seconds each). The benefit: every retained training example is human-validated. The training corpus quality dramatically exceeds the backfill quality.

Note: the user explicitly volunteered for this work. The doc reflects that commitment, but if scope pressures emerge, we can fall back to spot-checking only the contested cases (~150-300 records) rather than reviewing all retained examples.

### Class balancing — weighted loss

The PRINCIPLE-heavy distribution (~30% PRINCIPLE in the backfill) needs addressing. Without intervention, the LoRA learns "when in doubt, predict PRINCIPLE."

Decision: **inverse-frequency weighted loss** during training. Each class's weight is `1 / class_frequency`, normalized so weights average to 1.

Example: if PRINCIPLE is 30% of training data, its weight is 1/0.30 ≈ 3.33. If JUDGMENT is 3% of training data, its weight is 1/0.03 ≈ 33.3.

This corrects the bias mathematically without dropping data.

If after first training run we see PRINCIPLE still over-predicted, escalate to:
- **Squared inverse frequency** (more aggressive upweighting of rare classes)
- **Downsampling** of over-represented classes (smaller corpus but better balanced)
- **Synthetic augmentation** (v0.3+ if mathematical balancing isn't sufficient)

### Synthetic augmentation — deferred but planned

If weighted loss doesn't sufficiently correct the class skew, synthetic augmentation enters as an option. This is v0.3+ territory but worth documenting the approach now.

**Collaboration pattern with terminal Claude:**

1. Terminal Claude analyzes the curated training corpus and identifies the most underrepresented categories
2. Terminal Claude drafts proposed augmentation chunks — text that exemplifies each underrepresented category, written in the same style as the planning-docs corpus
3. User and I (collaboratively) review the drafted chunks — are these representative? Are they actually examples of the categories we say they are? Are they too generic / too specific / too unlike the existing corpus?
4. Adjustments made, iterating until the augmentation looks right
5. Approved synthetic examples added to the training corpus with clear metadata: `source: synthetic`, `generated_by: <model_name>`, `generated_date: <date>`, `approved_by: ryan`
6. Training proceeds with the augmented corpus
7. Per-class evaluation specifically watches for synthetic-class over-prediction (signal of distribution shift)

**Safeguards if used:**
- Synthetic examples always tagged for identification
- Synthetic ratio cap (≤20% of training data is synthetic)
- Per-class evaluation watches for synthetic-class over-prediction
- Held-out evaluation uses only non-synthetic chunks (so we measure generalization to real data, not to our own synthetic distribution)

This stays out of v0.2 unless weighted loss proves insufficient.

### Format

Two corpora because of the two-pass architecture:

**Pass 1 corpus (quadrant classification):**

```jsonl
{"prompt": "<pass1 quadrant prompt with chunk>", "completion": "<JSON with quadrant + scores>"}
```

**Pass 2 corpus (within-quadrant classification):**

```jsonl
{"prompt": "<pass2 within-quadrant prompt with chunk>", "completion": "<JSON with primary + scores>"}
```

Total: ~1,200-1,400 prompt/completion pairs (each curated chunk produces one Pass 1 example and one Pass 2 example).

Both corpora train the same LoRA adapter. The adapter learns both tasks from the same weights, using the prompt structure to distinguish them.

### Train/validation/test split

From the curated ~600-700 examples:

- **Training set:** 80% (~500-560 examples)
- **Validation set:** 10% (~60-70 examples) — used during training to monitor for overfitting, not for final evaluation
- **Held-out test set:** 10% (~60-70 examples) — never seen during training, used only for final evaluation

Plus the 30 hand-labeled calibration fixtures stay completely separate from train/val/test as the gold-standard evaluation set. **They are excluded from training** in v0.2.0.

Stratify the splits by D1 category so each split has roughly proportional representation.

### Data hygiene checks

Before training begins, validate:

- No exact duplicates between train and held-out sets
- No near-duplicates (same chunk content with whitespace differences)
- Each split has all 16 D1 categories represented
- The 30 calibration fixtures don't appear anywhere in the training data
- Pass 1 and Pass 2 examples for the same chunk go to the same split (don't put Pass 1 in train and Pass 2 in test for the same chunk — that's data leakage)

## Model selection

**Base model:** `ibm-granite/granite-4.1-3b-base` (the actual base variant, not the instruct version we have in production).

**Reasoning:**

1. Empirically the best substrate (Round 2 calibration: 58% partial / 73% Pass 1 quadrant baseline accuracy, best of 13 models tested)
2. Same family as v0.1.0 production (Granite 4.1 3B instruct), so the LoRA-tuned base sits alongside an existing-and-validated production deployment
3. Base variant is the cleaner LoRA target (instruct variants are already shaped by training; LoRA on top has unpredictable interactions)
4. Dense architecture (no MoE complications)
5. Apache 2.0 license
6. Comfortably fits in 12GB VRAM for QLoRA training

**Fallback:** OLMo 3 7B base if Granite training fails to converge or shows pathological behavior. OLMo 3 has unique advantages (full training transparency, OlmoTrace) that become valuable for diagnostic work.

### Pre-training step — base vs instruct comparison

Before starting LoRA training, run a side-by-side comparison of Granite 4.1 3B base and Granite 4.1 3B instruct on the same evaluation set. This establishes the baseline more precisely.

Specifically:
- Pull `ibm-granite/granite-4.1-3b-base` (already done: Unsloth GGUF works)
- Verify it loads cleanly in Ollama for inference
- Run the v0.1.0 calibration test against both base and instruct variants
- Capture: strict accuracy, partial accuracy, Pass 1 quadrant accuracy, Pass 2 within-quadrant accuracy, latency

Why this matters: we currently know what the **instruct** variant scores (58% partial / 73% Pass 1 quadrant, per Round 2). We don't know what the **base** variant scores. The LoRA gets trained on top of the base. So we need to know the base baseline to honestly attribute improvements to "LoRA effect" rather than "base vs instruct effect."

Expected outcome: base scores slightly lower than instruct (no instruction tuning to help prompt-following), but with a smaller gap than off-the-shelf models would have. The gap is the "room for LoRA to recover and exceed."

## Training methodology

**Framework:** Unsloth + transformers for QLoRA training.

**Why Unsloth specifically:**
- 2-5× faster than vanilla transformers on the same hardware
- Designed for QLoRA on consumer GPUs
- Well-documented with working notebook examples
- Active maintenance and community
- Documented support for Granite 4.1 family

**Training type:** QLoRA (Quantized LoRA).

- Base model loaded in 4-bit (NF4 quantization)
- LoRA adapter weights in higher precision (typically bf16)
- Training updates only the adapter weights
- Base weights stay frozen at 4-bit precision

This is the standard configuration for fine-tuning on 12GB VRAM with a 3B-parameter base.

### Tiny sandbox run — before real training

Before running on the curated corpus, validate the Unsloth setup with a throwaway experiment:

- Pull the Unsloth example notebook for QLoRA fine-tuning
- Adapt it minimally to use Granite 4.1 3B base
- Train on ~50 random chunks from the backfill (no curation, no class balancing)
- Verify: training runs without crashes, loss decreases, output is produced, evaluation runs

This is a "does the machinery work?" experiment, not a "does this produce a good model?" experiment. We don't keep the resulting adapter. We just confirm that the whole pipeline (data loading, training loop, evaluation, saving) functions end-to-end before committing to the real run.

Estimated time: ~30-60 minutes for the full pipeline test.

If the sandbox run fails, troubleshooting happens before we commit to the full curated training. If it succeeds, we proceed to real training with confidence the tooling is sound.

### Hyperparameters (initial ranges)

The exact values get tuned empirically, but here are reasonable starting ranges:

| Parameter | Starting value | Range to try if needed |
|-----------|---------------|------------------------|
| LoRA rank (r) | 16 | 8, 16, 32, 64 |
| LoRA alpha | 32 | 16, 32, 64 |
| Target modules | attention (q,k,v,o) | attention + MLP if accuracy plateaus |
| Learning rate | 2e-4 | 1e-4 to 3e-4 |
| Batch size | 1 | 1 (constrained by VRAM) |
| Gradient accumulation | 4-8 | adjust to get effective batch ~8 |
| Epochs | 3 | 2-5 |
| Warmup steps | 5 | 5-50 |
| Optimizer | AdamW 8-bit | AdamW 8-bit (Unsloth default) |
| Weight decay | 0.01 | 0 to 0.1 |
| Gradient checkpointing | enabled | enabled (required for VRAM) |
| Max sequence length | 2048 | 2048 (covers all our chunks) |
| Class weighting | inverse-frequency | inverse-frequency, can switch to squared if skew persists |

These are starting points from Unsloth's documented defaults for similar-sized models on similar-sized datasets. Real hyperparameters emerge from running a few experiments.

### Training time estimate

- Per-epoch wall time on RTX 4070 Super 12GB: ~10-15 minutes for ~500 training examples
- Full training (3 epochs): ~30-45 minutes
- Plus evaluation runs after each epoch: ~5 minutes each
- Total: ~45-75 minutes for a complete training run

Multiple training runs are likely as we tune. Plan for 4-6 hours total compute time across experimentation.

### VRAM budget

Expected peak VRAM during QLoRA training of Granite 4.1 3B:

- Base model (4-bit): ~2.5 GB
- LoRA adapter weights: ~50-200 MB depending on rank
- Optimizer state (AdamW 8-bit): ~200-500 MB
- Activations (with gradient checkpointing): ~3-5 GB
- Cuda overhead and PyTorch baseline: ~1-2 GB

Total peak: ~7-10 GB on a 12 GB card. Comfortable headroom.

## Evaluation strategy

Three-tier evaluation to triangulate quality, plus production observation as the fourth check.

### Tier 1 — Calibration fixtures (30 records, hand-labeled, Round 2 audit applied)

Same metrics as Phase 2 close-out:
- Strict accuracy (X/30)
- Partial-credit accuracy (X.5/30)
- 4-quadrant calibration table (high/low confidence × correct/wrong)
- Clear / Ambiguous / Hard breakdown
- Pass 1 quadrant accuracy
- Pass 2 within-quadrant accuracy
- Per-category accuracy

Same metric set Phase 2 ran. v0.2 aims for 85%+ partial-credit on this tier.

### Tier 2 — Held-out test set (60-70 chunks from backfill, never seen during training)

Same metrics as Tier 1.

Why this matters: the calibration fixtures might over-represent specific framings or category boundaries. Held-out backfill chunks have the same distribution as production data — they tell us how the LoRA will actually behave when classifying new ingest.

v0.2 success requires Tier 2 accuracy matching or exceeding Tier 1 accuracy. If Tier 1 is 90% but Tier 2 is 60%, the model is overfit to specific calibration patterns.

### Tier 3 — Cross-model agreement on production-like chunks (100+ chunks)

Run the LoRA-tuned classifier on 100+ randomly-selected chunks that the LoRA never saw. Also run them through 2-3 other models (Qwen 3.5 9B, Llama 3.1 8B, Granite 4.0 Micro). Measure:

- LoRA agreement with cross-model consensus
- LoRA confidence on agreement vs disagreement cases
- Per-category agreement rates

Why this matters: Tier 1 and Tier 2 measure against our labels. Tier 3 measures against a different "ground truth" — what diverse other models think. If LoRA dramatically disagrees with the cross-model consensus, that's a flag.

The asymmetric case is also useful: if cross-model consensus is wrong (which Round 2 audit showed happens), and LoRA agrees with the cross-model consensus, that's still informative — the LoRA is at least behaving like a typical model, not in some weird drift state.

### Tier 4 — Production observation (ongoing, post-deployment)

After v0.2 ships:

- Use the LoRA-tuned model on real ingest
- Spot-check classifications manually (sampled, not exhaustive)
- Watch for systematic patterns of wrongness
- Compare against user expectations of what the classifier should do

Tier 4 is the real test. Tiers 1-3 are approximations of Tier 4. When Tier 4 surprises us, Tiers 1-3 had blind spots, and the test design itself gets updated.

### Comparison points for every evaluation run

For each evaluation, compare against:

1. **v0.1.0 production** (Granite 4.1 3B instruct, no LoRA)
2. **Pre-LoRA Granite 4.1 3B base** (the actual base variant we're training on, no fine-tuning)
3. **Best non-Granite alternative** (Qwen 3.5 9B as representative)

We want to see: LoRA-tuned Granite 4.1 3B significantly beats all three.

### Quality guards

These prevent declaring victory based on misleading metrics:

- **Per-category breakdown required.** Aggregate accuracy improvements that hide skew are not improvements.
- **Confidence calibration required.** Accuracy improving with broken confidence is failure.
- **Determinism check required.** Run the same 20 chunks twice and verify identical outputs at temperature 0.0.
- **Manual spot-check required after each iteration.** Hand-read 20 LoRA outputs against chunk content. Look for cases where the classification is technically wrong but plausibly correct, OR technically correct but the reasoning seems off.
- **Sanity check on Tier 3.** Cross-model agreement should improve, not degrade.

### The user's role in evaluation

The user has explicitly committed to manual spot-checking. Where automated metrics might miss subtle problems, human reading catches them. The collaboration pattern:

1. After each LoRA iteration, I (or terminal Claude) provide 20 random outputs with chunk content alongside
2. User reads each, makes verdict: reasonable / questionable / obviously wrong
3. We discuss any patterns in the questionable/wrong cases
4. Findings inform the next iteration's training or evaluation design

This is the loop that catches blind spots in the automated tests.

## Feedback loop and test validity

How we keep evaluation honest as the model improves.

### The structural challenge

Tests measure what their design lets them measure. A test designed in 2026 against current understanding of "good classification" will have blind spots that only become visible when the classifier produces outputs that surprise us.

This is normal. Every test in every project has this property. The honest engineering response isn't to demand perfect tests upfront; it's to set up a feedback loop where tests improve as understanding does.

### The loop

```
1. Train LoRA iteration
2. Evaluate against Tiers 1, 2, 3
3. Run manual spot-check
4. Compare automated results to spot-check findings
5. Where they agree → trust the automated result
6. Where they disagree → automated test has a blind spot; investigate
7. Update test design when blind spots are confirmed
8. Repeat
```

The key property: we never trust automated tests alone. We always have a secondary source of truth (manual spot-check, cross-model agreement, production observation) that can flag when automated tests are misleading us.

### What "test got updated" actually means

When a test has a confirmed blind spot, several things can happen:

- **Add a new fixture** that exemplifies the blind-spot case, so the next evaluation includes it
- **Reweight existing metrics** so the blind spot doesn't dominate scoring
- **Add a new metric** that specifically measures the previously-invisible dimension
- **Update label assignments** if the audit reveals the old labels were the problem (Round 2 fixture audit was an example)
- **Document the limitation** if the blind spot can't be cleanly fixed, so future work knows about it

The goal isn't perfect tests; it's tests that improve faster than the model's capabilities exceed them.

### What v0.3 evaluation will probably look like

Predicting forward, v0.2 evaluation will have blind spots that v0.3 work surfaces. Likely v0.3 evaluation will:

- Have a larger calibration set (100+ fixtures vs 30) with deliberate coverage of confusable pairs
- Use a more sophisticated scoring rubric (not just primary category match, but also alternative-category match probabilities)
- Include cross-domain evaluation (chunks from different source types, not just planning docs)
- Have explicit metrics for per-pair disambiguation quality
- Track confidence-vs-accuracy calibration more rigorously

This is not v0.2 work. v0.2 uses the current evaluation. v0.3 inherits whatever blind spots v0.2 surfaces.

## Deployment path

How the LoRA-tuned model gets into production.

### Two options

**Option A — Adapter loaded at inference time.**

Keep the base model + LoRA adapter as separate artifacts. Ollama supports this via Modelfile's `ADAPTER` directive.

Pros: smaller artifact (~200MB adapter), easier to swap adapters in/out for experimentation, base model reusable across multiple adapters.

Cons: slightly more complex Modelfile, slight inference overhead, less battle-tested than merged approach.

**Option B — Merged weights + GGUF conversion.**

Merge the LoRA into base weights, convert merged model to GGUF, run in Ollama like any other model.

Pros: standard Ollama deployment pattern (same as v0.1.0), no runtime adapter overhead, fully tested code path.

Cons: larger artifact (~2.5GB), can't swap adapters at runtime, GGUF conversion step adds setup work.

### Decision: Option B for v0.2 production

Reasoning:

- Same deployment pattern as v0.1.0
- Standard pattern, well-validated
- v0.2 is one adapter, so the "swap adapters" benefit of Option A doesn't apply yet
- v0.3+ multi-adapter scenarios become Option A territory

### Conversion and validation — every iteration

After **every** LoRA training iteration (not just the final candidate):

1. Merge LoRA adapter into base weights using Unsloth's merge utility
2. Save merged model in HF format
3. Convert merged model to GGUF using llama.cpp's conversion script
4. Quantize to Q4_K_M for consistency with v0.1.0 production
5. Import into Ollama via Modelfile
6. **Validate**: run the evaluation chunks through both the un-quantized HF model (post-merge) and the quantized GGUF (in Ollama). Outputs should be near-identical.

Why every iteration: quantization can subtly degrade fine-tuned model behavior in ways pre-quantization eval doesn't catch. Validating at every iteration catches this early. The cost is real (~10-15 minutes per iteration for conversion and validation) but prevents discovering quantization problems only at final candidate.

### Production swap

When the final candidate passes all evaluation tiers:

1. Add new model alias in LiteLLM config: `cerebra-classifier-v0-2-lora`
2. Keep v0.1.0 alias active for fallback
3. Run a 50-chunk validation through the production pipeline (same pattern as Phase 2's pre-backfill validation)
4. Swap the LLMAdapter default to the new alias
5. Bump PROMPT_VERSION to **v2.1.0** (prompts unchanged, model changed)
6. Document in deviation log
7. Standard merge gate flow

### On re-backfilling existing assignments

**Don't re-backfill existing v0.1.0 assignments in the v0.2.0 ship.** Schema supports re-classification (the `prompt_version` field exists for this), but we want to validate the LoRA in production on NEW chunks first.

A full re-backfill becomes v0.2.1 or v0.2.2, after we're confident the LoRA produces better classifications than v0.1.0. The criterion: spot-checking ~50 v0.2-classified-new-chunks vs ~50 v0.1.0-classified-existing-chunks shows the v0.2 model is meaningfully better.

## Risk and decision points

**Risk: training doesn't converge.**

Symptom: loss stays high, oscillates, or NaNs out.

Likely causes: learning rate too high, data quality too noisy, hyperparameter mismatch.

Response: drop LR by half, recheck data, reduce LoRA rank if model is over-capacity.

**Risk: training converges but accuracy doesn't improve.**

Symptom: training loss drops but evaluation accuracy stays at or below v0.1.0 baseline.

Likely causes: LoRA rank too low, targeting wrong modules, training data quality issues.

Response: bump rank to 32, add MLP layers to target modules, audit training data for systematic errors.

**Risk: evaluation improves but skewed.**

Symptom: aggregate accuracy lifts but per-category breakdown shows over-prediction of common classes or under-prediction of rare ones.

Likely causes: class balancing insufficient.

Response: increase class weight strength, switch to squared inverse-frequency, or escalate to synthetic augmentation in v0.3.

**Risk: evaluation improves but determinism breaks.**

Symptom: same chunk produces different outputs across runs at temperature 0.0.

Likely causes: training artifact introduced nondeterminism, sampling parameters not properly forced.

Response: investigate; if not fixable, model is unusable for production. Roll back to v0.1.0.

**Risk: result is good but production VRAM/latency unacceptable.**

Symptom: LoRA-merged model uses significantly more VRAM than v0.1.0 (>5GB) or takes >5 seconds per call.

Likely causes: rank too high, didn't quantize properly post-merge.

Response: re-quantize, or retrain with lower rank.

**Risk: Tier 1 improves but Tiers 2-3 don't follow.**

Symptom: calibration fixture accuracy lifts, but held-out chunks and cross-model agreement stay flat.

Likely causes: model overfit to specific patterns in the calibration set.

Response: this is a serious flag. Retrain with more diverse data or stop and reconsider training set construction.

**Risk: spot-check reveals problems automated evaluation missed.**

Symptom: numbers look great but reading 20 outputs shows weird patterns (e.g., model classifies based on word patterns rather than semantic content).

Response: the test has a blind spot. Update test design before continuing. This is the feedback loop in action.

### When to stop

We continue tuning if:
- Each iteration shows measurable improvement on Tier 2 held-out evaluation
- Per-category breakdown is stable or improving
- Determinism holds
- Spot-checks support the automated metrics

We stop and ship when:
- Tier 2 partial-credit accuracy ≥ 85%
- Tier 1 partial-credit accuracy doesn't regress significantly
- Tier 3 cross-model agreement ≥ baseline
- No category has dropped >5% from v0.1.0 baseline
- Determinism verified
- Manual spot-check shows no obviously-wrong patterns

We stop and reassess when:
- 3+ iterations without improvement
- Pathological behavior surfaces
- VRAM or latency problems can't be resolved
- Spot-check reveals systematic problems that automated metrics aren't catching

## Open questions

Things we haven't decided that need to be resolved during execution:

1. **Exact confidence threshold for Stage 1 curation.** Determined by inspecting the actual distribution of the 745 confidence scores.

2. **Whether the 30 calibration fixtures stay completely excluded.** v0.2.0 excludes them. If v0.2.x training plateaus, we might revisit and include them with held-out evaluation against a different fixture set.

3. **Exact class weighting strength.** Start with standard inverse-frequency, adjust based on first training run's per-category results.

4. **Whether synthetic augmentation enters v0.2 or stays deferred to v0.3.** Decision after first training run if weighted loss proves insufficient.

5. **Validation cadence.** Confirmed: every iteration gets full GGUF conversion and validation. Costly but catches quantization issues early.

6. **PROMPT_VERSION.** Confirmed: v2.1.0 for v0.2.0 ship. Prompts unchanged, model changed.

## Out of scope for v0.2

Deliberately deferred:

- **Counsel mode infrastructure.** v0.3+.
- **Per-pair disambiguation as separate training tracks.** v0.3+.
- **Continued pretraining (forking at mid-training stages, OLMo-style).** v0.5+.
- **Multi-adapter deployment with runtime switching.** v0.3+.
- **Synthetic data augmentation as primary technique.** Available as fallback if weighted loss insufficient.
- **Re-backfilling existing v0.1.0 SKU assignments.** v0.2.1 or later, only after LoRA validates in production.
- **Calibration set expansion to 100+ fixtures.** v0.3 work.
- **Cross-domain training data (chunks from non-planning sources).** v0.3+ when other source types ingest.

Listing what's NOT in scope keeps v0.2 bounded.

## What this doc commits to

Several decisions are firm enough that revisiting them requires explicit re-discussion:

- LoRA target model: Granite 4.1 3B base
- Training framework: Unsloth + transformers (QLoRA)
- Single adapter for both Pass 1 and Pass 2 tasks
- Curation through three-stage filter (confidence → cross-model consensus → comprehensive manual review)
- Class balancing via inverse-frequency weighted loss (first attempt)
- Deployment via Option B (merged + GGUF)
- Validation at every iteration (not just final candidate)
- Success threshold: 85%+ partial-credit accuracy on Tier 2 held-out evaluation
- Failure rollback: keep v0.1.0 production active until v0.2 validates
- PROMPT_VERSION = v2.1.0

If any change during execution, pause and update this doc.

## Implementation order

When execution starts, the natural sequence:

1. **Pull `ibm-granite/granite-4.1-3b-base`** to HF cache (via `hf download`)
2. **Verify base loads in Ollama** for inference
3. **Run base vs instruct comparison** on calibration set to establish baselines
4. **Tiny sandbox training run** with 50 random chunks — proves Unsloth pipeline works
5. **Run Stage 1 (confidence filtering)** on the 745 backfill records
6. **Run Stage 2 (cross-model consensus)** on Stage 1 survivors
7. **Run Stage 3 (comprehensive manual review)** — user-led
8. **Construct train/val/test split** with hygiene checks
9. **First real LoRA training run** with starting hyperparameters
10. **Evaluate on Tier 1, Tier 2, Tier 3**
11. **Manual spot-check** of 20 outputs
12. **Validate full conversion** (merge → GGUF → Ollama → eval)
13. **Iterate hyperparameters** based on results
14. **Repeat 9-12** until success criteria met or stopping criteria triggered
15. **Final candidate validation** through full production pipeline
16. **Deploy and validate** in production (50-chunk validation)
17. **Standard merge gate flow** for v0.2.0

Each step is bounded. Iteration happens at steps 13-14; everything else is mostly linear.

## What this doc doesn't say

Honest about what isn't here:

- **No tutorial on how Unsloth's API works.** That comes from running the Unsloth example notebook (step 4 in implementation order).

- **No deep theory of LoRA.** The LoRA paper and Unsloth docs cover this. Theory doesn't help us pick hyperparameters better than empirical iteration.

- **No deep theory of quantization.** Q4_K_M is the standard practical choice.

- **No detailed instructions for any tool.** Tool-specific commands emerge during execution from working notebooks and documentation.

These gaps are deliberate. They get filled by doing the work.

---

*Related docs:*
*- `docs/brainstorm/reframes/v01_as_substrate_for_lora.md` — why v0.1.0 was about training corpus quality*
*- `docs/brainstorm/reframes/cognitive_nature_as_perceptual_lens.md` — where this leads in v0.5+*
*- `docs/brainstorm/architecture/counsel_swarm_cognition.md` — multi-model infrastructure that v0.3+ uses*
*- `docs/agent/multi_model_comparison.md` and `_round2.md` — empirical foundation for model selection*
*- `docs/agent/deviations/v0.1.0.md` — Phase 2 close-out narrative*
