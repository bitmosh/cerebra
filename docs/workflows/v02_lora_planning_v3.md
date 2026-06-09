# Cerebra v0.2 — LoRA Training for SKU Classifier

*v3 revision. Reflects the redirect from manual Stage 3 review to consensus-only training with adaptive post-deployment correction. v0.1.0 quality principle preserved; the path to achieving it shifted.*

## What this doc is

The design plan for v0.2 Cerebra work: LoRA fine-tuning the SKU classifier on Phase 2's backfill corpus to lift classification quality from v0.1.0's 65% partial-credit accuracy. This is the bridge from "we have a substrate" to "we have a fine-tuned classifier whose representations include the 16-category taxonomy."

This is *not* a tutorial on LoRA training, *not* a complete v0.5+ roadmap, and *not* a checklist for execution. It's the design decisions made with rationale, written down so implementation has a clear target.

## What changed from v2

The v2 plan included Stage 3 manual review of 583 records as the primary quality mechanism. That step proved to be unrealistic given current time constraints — the cognitive load of holding the 16-category taxonomy in working memory while reviewing dense chunks is high, and the 4-8 hour focused session it required isn't available right now.

The v3 plan replaces Stage 3 with:
- **Path A-lite training corpus**: consensus records + auto-corrected obvious-errors via deterministic Stage 2 rules
- **Layered post-deployment correction strategy**: data quality improves adaptively after v0.2 ships, anchored to real failure modes rather than upfront speculation

This is a scope redirect, not a quality compromise. The v0.1.0 principle ("architecturally correct, consistently maintaining the same tier of quality through development") holds. The mechanism for achieving it changed from "manual review upfront" to "adaptive correction post-deployment."

## Goal and success criteria

**Primary goal:** Lift the SKU classifier's partial-credit accuracy from 65% (v0.1.0 production baseline) to a meaningfully higher target on a held-out evaluation set that does NOT overlap with training data.

**Adjusted target threshold:** 75-85% partial-credit accuracy. The original v2 plan targeted 85%. With a smaller training corpus (Path A-lite produces ~235-255 records vs the v2 plan's ~600-700), reaching 85% may not be achievable in v0.2.0. We aim for 75% as floor, 85% as stretch goal. If we land between, that's still a meaningful improvement.

**Secondary goals (unchanged from v2):**

1. **Improved confidence calibration.** v0.1.0's Granite 4.1 3B already shows honest confidence behavior. v0.2 should preserve or improve this — high confidence should correlate with high accuracy.
2. **Reduced PRINCIPLE bias.** The training corpus is PRINCIPLE-heavy; without class balancing this gets reinforced. v0.2 should show roughly equal accuracy across categories, not skewed toward over-represented classes.
3. **Maintained determinism.** Same chunk → same SKU at temperature 0.0.
4. **Per-pair improvement on known confusables.** TECHNIQUE↔MECHANISM, CONSTRAINT↔PRINCIPLE, DESIGN↔TECHNIQUE, TOOL↔MECHANISM, CONTEXT↔DESIGN, OBSERVATION↔EVENT.

**Failure criteria (when we stop and reconsider):**

- LoRA-tuned model scores worse than v0.1.0 baseline on held-out evaluation
- LoRA training doesn't converge
- Determinism breaks
- VRAM or latency in production becomes unacceptable
- Per-category accuracy becomes more skewed, not less
- Spot-checks reveal systematic failure modes the automated metrics didn't catch

## On test validity — the philosophical foundation

Before any training, an honest acknowledgment: we don't fully know whether our tests measure what we want them to measure.

The 30 calibration fixtures are hand-labeled approximations of "correct classification." Two audits have already revised those labels when the data made it clear they were imperfect. More revisions are likely as v0.2+ work surfaces blind spots the current test design can't see.

This isn't a flaw to be fixed before training — it's a structural property of evaluation. Any test is a partial lens. The honest approach isn't to demand a perfect test before proceeding; it's to triangulate across multiple imperfect lenses and watch for places they disagree.

The principles we work under:

**Trust no single test.** When a single test says "this is good," look at additional surfaces (other tests, production behavior, manual spot-checks) before believing it.

**Treat divergence between test and reality as test signal.** If automated evaluation says the LoRA is great but spot-checking shows weird outputs, the test has a blind spot. Update the test, not just the model.

**Iterate the test design alongside the model design.** v0.2 evaluation will improve on v0.1.0's. v0.3 will improve on v0.2's. The test is never finished; it matures as understanding does.

**Manual spot-checks catch what automated metrics miss.** Numbers can show improvement that's actually skew or overfitting. Reading 20 actual model outputs against actual chunk content catches systematic problems no aggregate metric will surface.

## Training corpus construction — Path A-lite

The corpus is constructed from Stage 1 and Stage 2 outputs using deterministic rules, no manual review.

### Source data

- `stage1_filtered.jsonl` — 583 records that passed confidence threshold (≥0.70)
- `stage2_consensus.jsonl` — same 583 records with Stage 2 votes from Qwen 3.5 9B, Llama 3.1 8B, Granite 4.0 Micro

### Path A-lite construction rules

For each record in stage2_consensus.jsonl:

```
Rule 1 — CONSENSUS RECORDS (≥2 Stage 2 models agree with v0.1.0 label):
  → Include in training corpus
  → Use v0.1.0 label as ground truth
  → Estimated count: ~205 records

Rule 2 — UNANIMOUS DISAGREEMENT (all 3 Stage 2 models pick the same 
         NON-v0.1.0 label):
  → Include in training corpus
  → Use the Stage 2 unanimous label as corrected ground truth
  → Estimated count: ~30-50 records

Rule 3 — CONTESTED (≤1 Stage 2 model agrees with v0.1.0, no unanimous 
         alternative):
  → Exclude from training corpus
  → These chunks have genuine multi-faceted content; we lack the 
    judgment data to resolve them
  → Estimated count: ~280-340 records dropped

Final corpus estimate: ~235-255 records
```

### Why Path A-lite specifically

Three alternatives were considered:

```
Path A-strict:    consensus only (~205 records)
                  cleanest but smallest

Path A-lite:      consensus + unanimous correction (~235-255 records)
                  recovers obvious v0.1.0 errors using cross-model signal
                  
Path A-permissive: consensus + 2-of-3 majority correction (~350+ records)
                   includes cases where Stage 2 models lean a direction
                   risk: 2-of-3 may be shared bias, not validation
```

Path A-lite is the right tradeoff. The unanimous-disagreement records are cases where Granite 4.1 3B (v0.1.0) made a confident call that THREE architecturally different models all rejected in the same direction. That's not just disagreement — it's coordinated correction. Including those records as relabeled training data uses cross-model agreement legitimately.

Path A-permissive's 2-of-3 majority risk is real. Llama 3.1 8B's known OBSERVATION/PATTERN bias would propagate systematically through any rule that trusts a 2-of-3 majority. The unanimity requirement in Path A-lite specifically filters out single-model-bias propagation.

### Acknowledged limitations of Path A-lite

Documented honestly:

1. **Shared-bias risk.** The four models (v0.1.0 Granite, Qwen, Llama, Granite Micro) all trained on similar internet-scale corpora. They share more biases than they differ. Path A-lite cannot detect cases where all four agree on a wrong answer due to shared blind spots.

2. **No multi-faceted content captured.** Contested records often represent chunks with genuinely multiple defensible framings. Path A-lite drops these, losing the data that would have populated D2/D3 sub-classifications in v0.3+ work.

3. **Rare classes remain underrepresented.** TOOL (7), CONTEXT (5), GOAL (5), JUDGMENT (3), EVENT (2), AGENT (0) — Path A-lite doesn't fix the data scarcity for these. Weighted loss helps mathematically but can't create signal that isn't there.

4. **Smaller corpus means potentially lower ceiling.** 235-255 records is on the small side for LoRA training on a 16-way classifier. v0.2 may underperform v2 plan's 85% target.

These limitations are accepted as the cost of v0.2 shipping in available scope. They become inputs to the layered correction strategy below.

### Class balancing

The PRINCIPLE-heavy distribution still requires intervention. Without it, the LoRA learns "when in doubt, predict PRINCIPLE."

Decision: **inverse-frequency weighted loss** during training. Each class's weight is `1 / class_frequency`, normalized so weights average to 1.

Example: if PRINCIPLE is 30% of training data, its weight is 1/0.30 ≈ 3.33. If JUDGMENT is 1% of training data, its weight is 1/0.01 = 100.

If after first training run PRINCIPLE is still over-predicted, escalate to:
- Squared inverse frequency (more aggressive)
- Downsampling of over-represented classes

### Format

Two corpora because of the two-pass architecture:

```
Pass 1 corpus (quadrant classification):
{"prompt": "<pass1 quadrant prompt with chunk>", 
 "completion": "<JSON with quadrant + scores>"}

Pass 2 corpus (within-quadrant classification):
{"prompt": "<pass2 within-quadrant prompt with chunk>",
 "completion": "<JSON with primary + scores>"}
```

Total: ~470-510 prompt/completion pairs (each chunk produces one Pass 1 example and one Pass 2 example).

Both corpora train the same LoRA adapter.

### Train/validation/test split

From the ~235-255 curated examples:

- **Training set:** 80% (~190-205 examples)
- **Validation set:** 10% (~24-26 examples) — monitor training, not final eval
- **Held-out test set:** 10% (~24-26 examples) — final evaluation only

Plus the 30 hand-labeled calibration fixtures stay completely separate. **Excluded from training.**

Stratify splits by D1 category so each split has roughly proportional representation.

### Data hygiene checks

Before training:
- No exact duplicates between train and held-out sets
- No near-duplicates (whitespace differences)
- Each split has all categories represented (where possible — rare classes may not survive split)
- The 30 calibration fixtures don't appear anywhere in training
- Pass 1 and Pass 2 examples for the same chunk go to the same split (avoid data leakage)

## Model selection

**Base model:** `ibm-granite/granite-4.1-3b-base` (the actual base variant).

**Reasoning (unchanged from v2):**

1. Empirically the best substrate (Round 2 calibration: best of 13 models)
2. Same family as v0.1.0 production
3. Base variant cleaner LoRA target than instruct
4. Dense architecture (no MoE)
5. Apache 2.0 license
6. Fits in 12GB VRAM for QLoRA

**Fallback:** OLMo 3 7B base if Granite training fails or shows pathological behavior.

### Pre-training step — base vs instruct comparison

Before LoRA training, run a side-by-side comparison of Granite 4.1 3B base and instruct on the calibration fixtures via Python/Unsloth inference (no Ollama, since base GGUF doesn't exist).

Why: we know what instruct scores. We don't know what base scores. The LoRA gets trained on top of base. We need that baseline to honestly attribute improvements.

## Training methodology

**Framework:** Unsloth + transformers for QLoRA training.

**Training type:** QLoRA (Quantized LoRA). Base model in 4-bit, LoRA adapter in bf16.

### Tiny sandbox run — before real training

Validate Unsloth setup with throwaway experiment: 50 random chunks, no curation, no class balancing. Verify training runs, loss decreases, evaluation completes.

Time estimate: ~30-60 minutes. We don't keep the resulting adapter.

### Hyperparameters (starting points)

| Parameter | Starting value | Range to try |
|-----------|---------------|--------------|
| LoRA rank (r) | 16 | 8, 16, 32, 64 |
| LoRA alpha | 32 | 16, 32, 64 |
| Target modules | attention (q,k,v,o) | + MLP if accuracy plateaus |
| Learning rate | 2e-4 | 1e-4 to 3e-4 |
| Batch size | 1 | 1 (VRAM constrained) |
| Gradient accumulation | 4-8 | adjust for effective batch ~8 |
| Epochs | 3 | 2-5 |
| Warmup steps | 5 | 5-50 |
| Optimizer | AdamW 8-bit | (Unsloth default) |
| Weight decay | 0.01 | 0 to 0.1 |
| Gradient checkpointing | enabled | required for VRAM |
| Max sequence length | 2048 | covers all chunks |
| Class weighting | inverse-frequency | switch to squared if skew persists |

### Training time and VRAM

- Per epoch: ~5-10 minutes on RTX 4070 SUPER with smaller corpus
- Full 3-epoch training: ~20-30 minutes
- Plus validation eval per epoch: ~5 minutes each
- Total per run: ~35-45 minutes
- Multiple runs expected: plan for ~3-4 hours total compute

Peak VRAM estimate: 7-10 GB on 12GB card. Comfortable.

## Evaluation strategy

Three-tier evaluation plus production observation as fourth check.

### Tier 1 — Calibration fixtures (30 records, Round 2 audit applied)

Metrics:
- Strict accuracy (X/30)
- Partial-credit accuracy
- 4-quadrant calibration table
- Clear / Ambiguous / Hard breakdown
- Pass 1 quadrant accuracy
- Pass 2 within-quadrant accuracy
- Per-category accuracy

### Tier 2 — Held-out test set (24-26 chunks from Path A-lite corpus, never seen during training)

Same metrics as Tier 1.

v0.2 success requires Tier 2 accuracy matching or exceeding Tier 1. If Tier 1 is 90% but Tier 2 is 60%, the model is overfit to calibration patterns.

### Tier 3 — Cross-model agreement on production-like chunks (50-100 chunks)

Run LoRA-tuned classifier on chunks not in any training data. Also run through 2-3 other models. Measure:

- LoRA agreement with cross-model consensus
- LoRA confidence on agreement vs disagreement cases
- Per-category agreement rates

### Tier 4 — Production observation (post-deployment, ongoing)

Real ingest, spot-checks, pattern observation. See "Layered data improvement strategy" below.

### Comparison points

Every evaluation runs against:
1. v0.1.0 production (Granite 4.1 3B instruct, no LoRA)
2. Pre-LoRA Granite 4.1 3B base (the base variant we're training on)
3. Best non-Granite alternative (Qwen 3.5 9B as representative)

### Quality guards

- Per-category breakdown required (aggregate hides skew)
- Confidence calibration required (broken confidence ≠ improvement)
- Determinism check required
- Manual spot-check after each iteration (20 random outputs read by hand)
- Tier 3 cross-model agreement should improve, not degrade

## Feedback loop and test validity

How we keep evaluation honest as the model improves.

### The loop

```
1. Train LoRA iteration
2. Evaluate against Tiers 1, 2, 3
3. Run manual spot-check (20 outputs)
4. Compare automated results to spot-check findings
5. Where they agree → trust the automated result
6. Where they disagree → automated test has a blind spot; investigate
7. Update test design when blind spots are confirmed
8. Repeat
```

The key property: we never trust automated tests alone. We always have a secondary source of truth (manual spot-check, cross-model agreement, production observation) that can flag when automated tests are misleading us.

## Layered data improvement strategy

The honest acknowledgment: Path A-lite ships v0.2 with known gaps. Those gaps don't get closed by Stage 3 manual review (that's deferred); they get closed by adaptive correction as evidence accumulates.

Five data sources, layered:

### Source 1 — Production observation

When you encounter LoRA outputs that are obviously wrong during normal Cerebra use, capture them. Build a "production failure" file of `(chunk, predicted, what_should_have_been)` triples.

```
cost: incremental, no separate work
trustworthiness: high — real-time judgment in context
volume: slow stream
applies to: long-term steady stream, not v0.3 batch input
```

### Source 2 — Disagreement-triggered correction queue

Modify the Cerebra classifier pipeline so chunks with confidence below threshold (default <0.5) or chunks where LoRA disagrees with parallel cross-model checks get flagged into `pending_review.jsonl`.

```
cost: 4-6 hours infrastructure work post-v0.2 ship
trustworthiness: high — focused on uncertain cases
volume: moderate, grows with usage
applies to: clean v0.3 training input
```

Implementation:

```python
# Cerebra config addition
confidence_review_threshold: 0.5
cross_model_check_enabled: true (optional)

# In classifier pipeline:
if confidence < confidence_review_threshold:
    flag_for_review(chunk, prediction, reason="low_confidence")
    
if cross_model_check_enabled and disagreement_detected:
    flag_for_review(chunk, prediction, reason="model_disagreement")
```

The stage3_review.py TUI we already built can be repurposed to clear this queue. Same interface, different input file.

### Source 3 — Adversarial probing of failure modes

After v0.2 ships, evaluate it. Identify systematic failure modes (e.g., "over-predicts PRINCIPLE on chunks containing 'must'"). Construct or curate small targeted batches that exercise the failure modes. Manually label those.

```
cost: medium — systematic eval + 30-60 min focused sessions
trustworthiness: high — labels produced with full context
volume: small but high-density per failure mode
applies to: surgical v0.3 corrective training
```

### Source 4 — New source ingestion brings genuinely new content

When Cerebra eventually ingests other content types (research notes, chat history, code, etc.), the LoRA hits content it wasn't trained on. Some outputs will be obviously wrong because content is genuinely different.

```
cost: organic — happens when scope expands
trustworthiness: variable
volume: grows naturally
applies to: v0.3+ in proportion to source diversification
```

### Source 5 — Cross-model voting on production chunks

For each new chunk LoRA classifies, also run through 2-3 other models. When models disagree with LoRA, that's signal stored to disagreement log.

```
cost: compute (3x classification per chunk)
trustworthiness: medium — disagreement is signal, not ground truth
volume: high
applies to: ongoing "where did LoRA diverge from family" signal
```

### Combined strategy

```
NOW (v0.2 ship): nothing extra required
  → just train Path A-lite and deploy with documented limitations

IMMEDIATELY POST-SHIP: source 2 infrastructure
  → 4-6 hours to build the flagging mechanism + queue review tooling
  → low-confidence and high-disagreement chunks accumulate

ONGOING: sources 1 + 5
  → 1 happens automatically during Cerebra use
  → 5 happens at compute cost only
  → both feed into the same queue

FOR v0.3 PLANNING: sources 3 + 4
  → 3 happens when you have focused time for failure investigation
  → 4 happens when you naturally add new source types
```

The genius of this layering: **no single source requires committing a fixed block of time to manual review.** Each source either happens automatically (5), happens organically (1, 4), or happens when you choose to spend the attention (2, 3). The queue fills; you handle it when you can.

### Honest scope concern

The layered approach assumes you'll keep using Cerebra after v0.2 ships, and that you'll actually clear the queue periodically. If neither happens, the data doesn't accumulate. The system goes stale.

This is a real risk but a recoverable one. If the queue goes unmaintained, v0.2 remains the production state and you can revisit when you have attention. Path A-lite produced a working LoRA; the model doesn't degrade just because the improvement pipeline pauses.

## Deployment path

How the LoRA-tuned model gets into production.

### Option B (merged + GGUF) for v0.2

Same as v2 plan. Merge LoRA into base weights, convert to GGUF, run in Ollama like any other model.

Reasoning unchanged:
- Same deployment pattern as v0.1.0
- Standard, well-validated pattern
- v0.2 is one adapter, "swap adapters" benefit doesn't apply yet
- v0.3+ multi-adapter scenarios become Option A territory

### Conversion and validation — every iteration

After every LoRA training iteration (not just final candidate):

1. Merge LoRA into base weights via Unsloth merge utility
2. Save merged model in HF format
3. Convert to GGUF via llama.cpp conversion script
4. Quantize to Q4_K_M for consistency with v0.1.0
5. Import into Ollama via Modelfile
6. **Validate**: run evaluation chunks through both un-quantized HF model and quantized GGUF. Outputs should be near-identical.

Why every iteration: quantization can subtly degrade fine-tuned model behavior. Validating each iteration catches this early.

### Production swap

When final candidate passes all evaluation tiers:

1. Add new model alias: `cerebra-classifier-v0-2-lora`
2. Keep v0.1.0 alias active for fallback
3. Run 50-chunk validation through production pipeline
4. Swap LLMAdapter default to new alias
5. Bump PROMPT_VERSION to **v2.1.0**
6. Deploy correction queue infrastructure (source 2)
7. Document in deviation log
8. Standard merge gate flow

### On re-backfilling existing assignments

**Don't re-backfill in v0.2.0 ship.** Validate v0.2 on NEW ingest first. Re-backfill becomes v0.2.1 or v0.2.2 work once confidence in v0.2's improvement is established.

## Risk and decision points

What could go wrong and how we'd know.

**Risk: training doesn't converge.**

Symptom: loss stays high, oscillates, NaNs.
Causes: LR too high, data too noisy, hyperparameter mismatch.
Response: drop LR by half, recheck data, reduce LoRA rank.

**Risk: training converges but accuracy doesn't improve.**

Symptom: training loss drops, eval accuracy stays at/below v0.1.0.
Causes: rank too low, wrong target modules, training data quality.
Response: bump rank to 32, add MLP layers, audit training data.

**Risk: evaluation improves but skewed.**

Symptom: aggregate accuracy lifts but per-category breakdown shows over-prediction of common classes.
Causes: class balancing insufficient.
Response: increase weight strength, switch to squared inverse-frequency.

**Risk: corpus too small to train effectively.**

Symptom: training converges quickly to local minimum, validation accuracy plateaus low.
Causes: 235-255 records may not be enough for 16-way classification.
Response: consider Path A-permissive as fallback (with documented shared-bias risk), or accept lower target threshold (75% instead of 85%).

This is the v0.2-specific risk. If it materializes, we have options short of abandoning the approach.

**Risk: shared-bias amplification.**

Symptom: LoRA passes Tier 1 and 2 but spot-checks reveal systematic failure modes that match known biases of the model family.
Causes: training data inherited biases shared across the four consensus models.
Response: capture failure modes in the correction queue (source 2), use them for v0.3 training, document as v0.2 known limitation.

**Risk: determinism breaks.**

Symptom: same chunk produces different outputs across runs at temp=0.0.
Causes: training artifact, sampling parameters not forced.
Response: investigate; if not fixable, model unusable; roll back.

**Risk: result good in eval but degrades on real production chunks.**

Symptom: classifier great on held-out test set but produces weird outputs on new ingest.
Causes: test set wasn't representative; training over-fit to specific framings.
Response: this surfaces in source 1 (production observation). Roll back if severe; capture failures for v0.3.

### When to stop

We continue tuning if:
- Each iteration shows measurable improvement on Tier 2
- Per-category breakdown stable or improving
- Determinism holds
- Spot-checks support the automated metrics

We stop and ship when:
- Tier 2 partial-credit accuracy ≥ 75% (floor) or ≥ 85% (stretch)
- Tier 1 partial-credit accuracy doesn't regress significantly
- Tier 3 cross-model agreement ≥ baseline
- No category drops >5% from v0.1.0 baseline
- Determinism verified
- Manual spot-check shows no obviously-wrong patterns

We stop and reassess when:
- 3+ iterations without improvement
- Pathological behavior surfaces
- VRAM or latency problems can't be resolved
- Spot-check reveals systematic problems automated metrics aren't catching

## Open questions

1. **Exact confidence threshold for Stage 1.** Already determined empirically (0.70 retained 583/745 records, 78.3%). Settled.

2. **Class weighting strength.** Start with standard inverse-frequency, adjust based on first training run.

3. **PROMPT_VERSION.** Confirmed: v2.1.0 for v0.2.0.

4. **Whether to include calibration fixtures in training.** Excluded for v0.2.0. May revisit if training plateaus.

5. **Whether Path A-permissive becomes fallback.** Only if Path A-lite produces unworkably small corpus. Carries shared-bias risk that needs documentation.

6. **Stage 3 review revival.** Deferred indefinitely. Infrastructure (stage3_review.py) preserved for future use if attention becomes available.

## Out of scope for v0.2

Deliberately deferred:

- **Stage 3 manual review.** Infrastructure ready; deferred to future scope.
- **Counsel mode infrastructure.** v0.3+.
- **Per-pair disambiguation as separate training tracks.** v0.3+.
- **Continued pretraining (forking at mid-training stages, OLMo-style).** v0.5+.
- **Multi-adapter deployment with runtime switching.** v0.3+.
- **Synthetic data augmentation as primary technique.** Available as fallback.
- **Re-backfilling existing v0.1.0 SKU assignments.** v0.2.1 or later.
- **Calibration set expansion to 100+ fixtures.** v0.3 work.
- **Cross-domain training data.** v0.3+ when other source types ingest.
- **Conceptual topology probing at scale.** Methodology documented, deferred.
- **Disposition fingerprinting PoC.** Methodology documented, deferred.

Listing what's NOT in scope keeps v0.2 bounded.

## What this doc commits to

Decisions firm enough that revisiting requires explicit re-discussion:

- LoRA target model: Granite 4.1 3B base
- Training framework: Unsloth + transformers (QLoRA)
- Single adapter for both Pass 1 and Pass 2 tasks
- Training corpus: Path A-lite (consensus + unanimous-disagreement correction)
- Class balancing: inverse-frequency weighted loss
- Deployment: Option B (merged + GGUF)
- Validation: every iteration
- PROMPT_VERSION: v2.1.0
- Success threshold: 75% floor, 85% stretch on Tier 2 held-out evaluation
- Failure rollback: keep v0.1.0 production active until v0.2 validates
- Post-deployment: layered correction strategy with source 2 infrastructure as first build

If any change during execution, pause and update this doc.

## Implementation order

When execution starts, the natural sequence:

1. **Build training corpus** — `build_training_corpus.py` updated for Path A-lite rules
   - input: stage2_consensus.jsonl
   - apply Rule 1 + Rule 2
   - stratified train/val/test split
   - hygiene checks
   - output: train.jsonl, val.jsonl, test.jsonl, class_weights.json

2. **Pull `ibm-granite/granite-4.1-3b-base`** to HF cache (done)

3. **Run base vs instruct comparison** via Python/Unsloth inference on calibration fixtures

4. **Tiny sandbox training run** with 50 random chunks — proves Unsloth pipeline works

5. **First real LoRA training run** with starting hyperparameters

6. **Evaluate on Tier 1, Tier 2, Tier 3**

7. **Manual spot-check** of 20 outputs

8. **Full conversion validation** (merge → GGUF → Ollama → eval)

9. **Iterate hyperparameters** based on results

10. **Repeat 5-9** until success criteria met or stopping criteria triggered

11. **Final candidate validation** through full production pipeline

12. **Deploy and validate** in production (50-chunk validation)

13. **Build correction queue infrastructure** (source 2)

14. **Standard merge gate flow** for v0.2.0

Steps 1-12 are pre-ship work. Step 13 happens immediately post-ship to enable adaptive correction going forward.

## Honest acknowledgments

What this plan trades away:

- The depth of analysis Stage 3 review would have provided
- The ability to capture multi-faceted content as D2/D3 candidates upfront
- The 85% target as expected v0.2 outcome (may achieve, may not)
- The data-richness that comes from human-validated training corpus

What this plan gains:

- Ship-ability in available time
- Honest scope discipline
- Adaptive correction grounded in real failure modes
- Preserved methodology for future development
- v0.3 planning anchored to evidence rather than speculation

The redirect reflects a principle worth naming: **scope cuts that preserve quality are different from scope cuts that compromise quality.** Path A-lite + layered correction preserves quality by spreading data work across time rather than packing it upfront. The same quality emerges; the schedule differs.

This is consistent with the substrate-for-LoRA reframe. v0.2 produces an artifact, not a perfect classifier. Its limitations are documented. v0.3+ work iterates against real evidence rather than upfront speculation about what might be wrong.

---

*Related docs:*
*- `docs/brainstorm/reframes/v01_as_substrate_for_lora.md` — why v0.1.0 was about training corpus quality*
*- `docs/brainstorm/reframes/cognitive_nature_as_perceptual_lens.md` — where this leads in v0.5+*
*- `docs/brainstorm/architecture/counsel_swarm_cognition.md` — multi-model infrastructure that v0.3+ uses*
*- `docs/brainstorm/architecture/conceptual_topology_probing.md` — methodology preserved for future development*
*- `docs/brainstorm/architecture/model_disposition_fingerprinting.md` — methodology preserved for future development*
*- `docs/agent/multi_model_comparison.md` and `_round2.md` — empirical foundation for model selection*
*- `docs/agent/deviations/v0.1.0.md` — Phase 2 close-out narrative*
