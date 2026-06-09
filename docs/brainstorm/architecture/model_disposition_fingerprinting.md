# Model Disposition Fingerprinting — Three-Test Triangulation

*Drafted 2026-06-07. Status: methodology proposal. Not yet on dev path. Applications beyond Cerebra.*

## The core idea

Models have cognitive temperaments that emerge from training. These temperaments shape how they respond to ambiguity, where they default when uncertain, what categories they over-attend to, and how confidently they commit. Most model evaluation ignores these properties — it measures task accuracy and stops there.

This doc proposes a methodology for **observing model temperament directly**, with a specific three-test design that triangulates between:

1. **Disposition profiling (negative-space)** — model is not told it's being measured; behavior pattern reveals cognitive defaults
2. **Disposition profiling (explicit)** — model is told it's being evaluated for project selection; behavior pattern reveals how performance changes under observation
3. **Standard ML evaluation** — typical task accuracy metrics on the same model

The comparison across the three is the methodological contribution. Each test alone says something narrow. Together they form a fingerprint that captures cognitive shape, performative shape, and task capability — three different facets of "what kind of model is this."

## The "negative-space" framing

The term matters. We're not testing what the model can do explicitly. We're testing what it does *when there's no clear right answer to perform toward*.

```
explicit measurement:
  "what is 2+2?"
  → 4 (or wrong; either way the answer space is bounded)

negative-space measurement:
  "classify this ambiguous chunk that could plausibly be X, Y, or Z"
  → model picks one
  → the choice reveals disposition, not capability
  → the model doesn't know what's being measured
  → there's no "correct" answer to perform toward
```

What gets revealed:

- **Default lens.** When the chunk is genuinely ambiguous, what category does the model fall back to? Some models default to OBSERVATION (descriptive mode). Some default to PRINCIPLE (normative mode). The default IS the lens.
- **Threshold for commitment.** At what level of clarity does the model commit to a category? Some commit easily; some require strong signal.
- **Refusal patterns.** Does the model ever decline to commit? Or does it always pick something?
- **Confidence calibration.** Does confidence correlate with actual clarity, or is the model uniformly confident regardless of input?

## Why this differs from standard ML evaluation

```
standard ML eval                    disposition profiling
─────────────────                   ──────────────────────
measures: did model get the right    measures: what does model do when
          answer?                              right answer is unclear?

metric:   accuracy, F1, precision    metric:   distribution of choices,
                                               default attractors,
                                               confidence calibration

frames:   model as black box that    frames:   model as cognitive agent
          produces outputs                     with default dispositions

reveals:  capability                 reveals:  temperament
```

These are not in conflict. They measure different things. A model can be highly capable (good at standard eval) AND have problematic disposition (defaults to specific categories under ambiguity). Both matter, and they're separable.

The gap in current practice: standard eval is everywhere; disposition profiling is rare. Most systems that use LLMs as components don't profile cognitive disposition before selecting them. They pick based on capability metrics, then discover disposition issues later when production behavior surprises them.

## The three-test design

Each test runs the same model against carefully constructed stimuli. The difference is in the *frame* given to the model.

### Test 1 — Disposition (negative-space)

Model receives chunks in the standard production prompt. Same prompt structure used in v0.1.0 classification. Model believes it's doing its normal job.

```
prompt to model: "classify this chunk into the appropriate D1 category"
                 (standard v2.0.0 two-pass prompts)
chunk content: probe chunk at known clarity level
model output: classification + confidence
```

The model doesn't know:
- It's being evaluated
- The chunks were specifically constructed to test temperament
- The pattern of its responses is being analyzed

What's measured:
- Choice distribution across the 16 categories
- Default attractor (most common choice on level-5 ambiguous probes)
- Confidence calibration (does confidence track clarity?)
- Threshold for commitment (at what clarity level does the model stop defaulting?)

### Test 2 — Disposition (explicit)

Identical to Test 1 but with a system prompt that explicitly tells the model it's being evaluated for project selection.

```
prompt to model: "you are being evaluated for selection in a cognitive
                  classification project. classify this chunk into the
                  appropriate D1 category. your responses will be
                  reviewed for accuracy and appropriate confidence."
chunk content: same probe chunks, identical to Test 1
model output: classification + confidence
```

What changes (potentially):
- Models that "try harder" under observation
- Models that hedge confidence when watched
- Models that shift toward "safe" categories under pressure
- Models that introduce reasoning chains they wouldn't otherwise use

What's measured:
- Delta from Test 1 baseline (per-category, per-confidence, per-default)
- Direction of shift (toward caution? toward confidence? toward specific categories?)
- Consistency of shift (does the model shift uniformly or selectively?)

### Test 3 — Standard ML evaluation

Same model, same prompts, but stimuli are the standard 30 calibration fixtures with known correct labels. This is the existing calibration test.

```
prompt to model: standard v2.0.0 two-pass prompts
chunk content: 30 hand-labeled calibration fixtures
model output: classification + confidence
metric: accuracy (strict and partial-credit) against known labels
```

What's measured:
- Standard accuracy metrics
- Per-category accuracy
- Confidence calibration (4-quadrant table)

This is what we already run. Nothing new in the methodology — it's the baseline against which Tests 1 and 2 are compared.

## The triangulation

The interesting analysis is the cross-test comparison:

```
                Test 1          Test 2          Test 3
                (covert)        (explicit)      (capability)
                
default lens    revealed        revealed        not revealed
performance     revealed        revealed        revealed
under-watch     hidden          revealed        n/a
capability      partial         partial         primary signal
```

Cross-test patterns to look for:

**1 vs 3 — disposition vs capability divergence.**

A model that has strong disposition toward OBSERVATION (Test 1) but still scores 80% on standard eval (Test 3) is using OBSERVATION as a *useful* default — it tends to be right when defaulting. A model with the same disposition but only 50% accuracy is using OBSERVATION as a *lazy* default — it's defaulting because of training bias, not because OBSERVATION is the right answer.

Same disposition, different capability. Same lens, different sharpness.

**1 vs 2 — natural vs performative behavior.**

A model whose Test 1 and Test 2 results are nearly identical has consistent behavior regardless of observation. Trustworthy in production.

A model whose Test 2 results dramatically differ from Test 1 is *performing* when watched. Maybe better, maybe worse — but inconsistent. This is a flag for production deployment: the eval-time behavior won't match the production behavior because evals are observed.

This is also a tell for model alignment. Models heavily RLHF'd to perform well in evaluations may show large Test 1/Test 2 deltas — they've learned to "look good on tests" rather than respond consistently.

**2 vs 3 — performative response shape.**

Test 2 (explicit) on probe chunks vs Test 3 (capability) on labeled fixtures — both are observed conditions. The pattern shift between them reveals what the model does when it knows answers are clearer (Test 3) vs when answers are deliberately murky (Test 2 with ambiguous probes).

If Test 3 accuracy is high but Test 2 shows wild category defaults on ambiguous probes, the model can perform on clear inputs but lacks honest uncertainty signaling.

**All three together — full cognitive fingerprint.**

A model can be characterized along three independent axes:
- Capability (Test 3 accuracy)
- Natural disposition (Test 1 pattern)
- Performative shift (Test 2 minus Test 1 delta)

Different production needs prioritize different axes. Cerebra's "model as substrate, not thinker" philosophy values low performative shift (consistent behavior) and high natural disposition diversity across counsel members. Other systems might prioritize raw capability.

## Probe corpus construction

The corpus is the hard part of the methodology. Probes must be carefully constructed to occupy specific clarity levels.

**Five-level clarity scale (per category):**

```
Level 1 — literal match
  text explicitly invokes the category by name or canonical pattern
  example for MECHANISM:
    "The classifier uses a two-pass mechanism: first quadrant
     selection, then within-quadrant disambiguation."

Level 2 — strong fit
  clearly this category, no other reasonable read
  example for MECHANISM:
    "When the request fails, the retry handler waits an exponentially
     increasing duration before attempting again."

Level 3 — mixed
  this category plus one other equally valid
  example for MECHANISM (also valid as DESIGN):
    "The system inverts the typical authorization flow:
     permissions are denied by default and granted explicitly."

Level 4 — weak signal
  could be this, could be 2-3 others
  example for MECHANISM (also TECHNIQUE, also DESIGN):
    "Configuration changes propagate through the cluster via gossip,
     with eventual consistency guarantees."

Level 5 — genuinely ambiguous
  framing is neutral; all categories equally plausible
  example for MECHANISM (or anything):
    "The component does what it's designed to do under expected
     conditions, with predictable behavior."
```

For each of the 16 D1 categories, construct 5 probes at the five clarity levels. Total corpus: 80 probes.

**Construction principles:**

- Length consistent across levels (avoid confounding clarity with length)
- Same source style across all probes (planning-doc voice; avoid format confounds)
- No category names appear verbatim in the probe text (would prime models toward that category)
- Level 5 probes are genuinely category-neutral — the framing favors no particular D1
- Level 1 probes are clear without being trivial — vocabulary aligns but doesn't restate the definition

**Construction workflow (collaboration pattern):**

```
1. Terminal Claude drafts probe candidates per category × level
2. We review each — does it actually sit at the claimed clarity level?
3. Multiple revisions; some probes get demoted (level 2 → level 3) when
   review reveals they're more ambiguous than initially thought
4. Final corpus reviewed by reading each probe out of order
   (without seeing claimed level) and trying to rate it ourselves —
   does our intuition match the assigned level?
```

This is real construction work. Estimate ~6-10 hours for 80 high-quality probes.

## Methodological precautions

**Order randomization.**

Run probes in randomized order. Don't run all PRINCIPLE probes back-to-back, then all MECHANISM probes. The model has no conversation state between calls, but our analysis might detect patterns that are artifacts of grouping.

Run 3 random shuffles per model. Aggregate across shuffles.

**Multiple runs at temp=0.0.**

We've confirmed perfect determinism at temp=0.0 across 13 models in Round 1/Round 2. So 3 identical runs at temp=0.0 are redundant — they'll produce identical outputs. ONE run per shuffle is sufficient.

If a model breaks determinism at temp=0.0, that itself is signal — flag and document.

**Cold-state requirement.**

Each probe is a fresh chat session with no carried context. The same model loaded into Ollama for the first probe of the day should be effectively identical to the same model running probe #80 of the day. Verify by sampling.

**Cross-model prompt invariance.**

The same prompt structure for all models. Don't tune prompts per model. We're measuring the model's behavior on identical stimuli; prompt variation is a confound.

This is one place where the v2.0.0 two-pass prompts may not be ideal — they're optimized for Granite 4.1 3B's behavior. For pure disposition profiling, a simpler "classify this into one of these 16 categories" prompt would isolate disposition better. Worth experimenting with both.

**The explicit-test prompt for Test 2.**

The "you are being evaluated for selection" framing must be:
- Truthful (we ARE evaluating for project selection)
- Specific enough that the model treats it differently from normal classification
- Generic enough that we can use the same framing across all models

Draft framing:

```
You are being evaluated for selection in a cognitive classification
project. The project requires accurate categorization of text chunks
into 16 fine-grained categories representing different kinds of
knowledge content. Your classifications will be reviewed for accuracy
and appropriate confidence calibration. Please classify the following
chunk into the most appropriate D1 category and report your confidence.
```

Specifically: tells the model it's being evaluated, names the stakes (selection in a project), invokes "accuracy and appropriate confidence" as criteria — this is what triggers performative shifts if the model has them.

## What we expect to see

Predictions worth testing:

**1. Llama 3.1 8B will show strong OBSERVATION/PATTERN bias on Test 1 level-5 probes.**

Stage 2 data already suggests this. Disposition profiling should make it explicit and quantifiable.

**2. Granite 4.1 3B will show calibrated confidence on Test 1 ambiguous probes.**

Validation report showed honest low-confidence behavior on short ambiguous chunks. Should generalize.

**3. Qwen 3.5 9B will show large Test 1/Test 2 delta.**

Hypothesis: heavily-instruction-tuned models with thinking modes are more performative under observation. Worth testing.

**4. Hermes 3 will show "personality" effects.**

Community fine-tuned for specific behaviors. Predict disposition shifts in idiosyncratic directions.

**5. Smaller models (qwen3.5:2b, qwen3.5:0.8b) will show flat disposition (low entropy across categories).**

Less capacity = less developed defaults. Probably just collapse to most common category in training data.

These are predictions to test, not conclusions. The probe corpus + three-test methodology either confirms or refutes them.

## Applications beyond Cerebra

The methodology is generalizable. Any system that uses LLMs as components could benefit from disposition profiling its candidates before selection.

```
relevant application areas:
─────────────────────────
- multi-agent systems where models collaborate
  → disposition diversity matters for productive disagreement
- routing/triage systems
  → match disposition to task type
- evaluation/grading systems
  → understand the model's default lens before using it as a judge
- counsel/swarm cognition (Cerebra v0.3+)
  → empirical basis for selecting counsel members
- LoRA fine-tuning targets
  → measure disposition shift caused by training
```

The probe corpus would need to be redesigned per domain. The 16-category Cerebra taxonomy is specific to our taxonomy; another domain would have different categories. But the methodology — graduated probes, three-test design, cross-test triangulation — transfers cleanly.

This is publishable methodology. Not in v0.2 critical path, but a contribution to the field if eventually written up properly.

## Connection to other brainstorm docs

This composes with the existing brainstorm content:

**`counsel_swarm_cognition.md`** — disposition profiling is the empirical basis for counsel member selection. Without disposition data, counsel selection is based on architectural family diversity (a proxy). With disposition data, counsel selection optimizes for default-lens diversity (the actual property we want).

**`cognitive_nature_as_perceptual_lens.md`** — disposition profiling measures *current* cognitive nature. LoRA training changes cognitive nature. Repeat disposition profiling before and after training to see *what changed*. This is the empirical link from "we trained the model" to "the model's perceptual structure shifted in measurable ways."

**`triangle_balance_perception_understanding.md`** — disposition is the model's perceptual lens, which is one corner of the triangle. Profiling the lens makes the philosophical framework concrete.

**`two_thinking_systems_disruption.md`** — models with thinking modes likely show large Test 1/Test 2 deltas (performative shift under observation). Disposition profiling would empirically validate the substrate-not-thinking philosophy by showing that reasoning-enabled models are less behaviorally consistent.

## When to do this work

Not v0.2 critical path. Honest timing:

```
now:           Stage 3 manual review of 583 records (v0.2 work)
near:          LoRA training, evaluation, deployment (v0.2 ship)
after v0.2:    BUILD THE PROBE CORPUS — this is the slow part
post-LoRA:     run disposition profiling on:
               - pre-LoRA Granite 4.1 3B base
               - post-LoRA Granite 4.1 3B + adapter
               - measure what training changed
v0.3+:         use disposition data to select counsel members
               also: profile new candidate models as they appear
```

The probe corpus is the long-lead artifact. Build it once, use it forever (with periodic updates as the taxonomy or domain evolves). Construction can start during v0.2 LoRA training compute (Stage 3 is the bottleneck for now, not Stage 4+ work).

## What this doc commits to

- Three-test triangulation (covert / explicit / standard) is the right methodology
- 16 categories × 5 clarity levels = 80-probe corpus is the right scope
- Probe construction is collaborative (terminal Claude drafts, we review/refine)
- Probes must NOT contain category names verbatim
- Order randomization is required
- Cross-test comparison is where the insight lives — single-test results are partial
- This work is post-v0.2, not during

## Open questions

Resolved during execution:

1. **Should the v2.0.0 two-pass prompts be used, or a simpler "pick one of 16" prompt?** Probably try both — they may reveal different aspects of disposition.

2. **How to score "default attractor" mathematically?** Most-common category on level-5 probes is the simplest measure. Could also use entropy of the choice distribution (low entropy = strong default; high entropy = no clear default).

3. **What's the right Test 2 framing?** Initial draft above; may need iteration to actually trigger performative responses without being heavy-handed.

4. **How many probes per level is enough?** 5 categories × 5 levels = 25 probes per category, but we proposed 1 per level. Maybe 2 or 3 per level for redundancy. Trade-off: corpus quality vs. corpus size.

5. **Should Test 2 explicit framing be at the system-prompt level or interleaved across the conversation?** System prompt is cleaner; conversation-level framing might reveal different behavior. Probably test both.

6. **How to handle models that refuse to commit?** Some models (especially smaller ones) may output "I can't determine this" or null. Count these as a separate category in the choice distribution — they're meaningful signal about disposition.

## Methodological honesty

A few things to be explicit about so we don't oversell:

- **Single-shot probing has limits.** A model's response to one probe at one moment isn't the model's full disposition. Multiple probes per level and aggregation are required.
- **Disposition can shift with prompts.** What we measure is "disposition under THIS prompt structure" — not absolute cognitive temperament. Different prompt structures may reveal different defaults.
- **Cross-model comparison requires identical conditions.** Same prompts, same temperature, same context window, same ordering. Any variation is a confound.
- **The 5-level clarity scale is subjective.** Two humans rating the same probe may disagree on its level. Construction process must include calibration between reviewers.
- **Disposition is not stable across versions.** A model's disposition can shift between training releases. Profiling needs to be re-done when models update.

These are limitations, not refutations. They define the scope within which the methodology is meaningful.

## Bottom line

Disposition profiling is a real methodological gap in current ML practice. The three-test triangulation (covert / explicit / standard) is the design that captures what single-test approaches miss. The probe corpus is the long-lead construction artifact. The methodology is reusable across domains.

For Cerebra specifically: this becomes the empirical foundation for counsel mode (v0.3+), the diagnostic tool for LoRA training effects, and the basis for honest model selection going forward. We can stop picking models based on benchmark accuracy and start picking them based on architectural fit + disposition fit.

It's not v0.2 critical path. It's v0.3+ infrastructure. But the brainstorm should exist now while the thinking is fresh.

---

*See also:*
*- `architecture/counsel_swarm_cognition.md` — empirical basis for counsel selection*
*- `reframes/cognitive_nature_as_perceptual_lens.md` — disposition shift via training*
*- `philosophy/triangle_balance_perception_understanding.md` — perception as the model's lens*
*- `reframes/two_thinking_systems_disruption.md` — performative vs natural behavior*
