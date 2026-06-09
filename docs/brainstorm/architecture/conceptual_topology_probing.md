# Conceptual Topology Probing — Methodology & Proof-of-Concept Results

*Drafted 2026-06-08 immediately following the proof-of-concept run. Companion to `model_disposition_fingerprinting.md`. Methodology validated; scaling decisions pending.*

## What this doc is

A methodology for measuring what a model *actually understands* about a category, separate from whether it picks the "right" label. Built on the observation that when a model picks a "wrong" answer, it may be seeing a different but defensible facet of the same content. The question is whether those alternative readings trace coherent conceptual structure (genuine multi-faceted understanding) or random fragments (surface pattern matching).

The methodology validates: it produces signal that aggregate accuracy hides.

## The core observation behind the work

Standard ML evaluation treats classification as right/wrong against ground truth labels. This frame collapses two genuinely different failure modes:

```
failure mode 1 — surface pattern matching:
  model picks a category because of keyword cues, syntactic patterns,
  or surface features. The model doesn't have a conceptual model of
  the category; it has a lookup table.
  
  diagnostic: when "wrong," reasoning is generic, hedged, or evasive.

failure mode 2 — vocabulary boundary:
  model has a conceptual model of the category but uses different
  vocabulary to label it. "Design pattern" maps to TECHNIQUE in
  some models, to DESIGN in others, based on which framing is
  more strongly weighted in training data.
  
  diagnostic: when "wrong," reasoning references the SAME concepts
  as the "right" answer would, just labeled differently.
```

These two failure modes look identical in accuracy metrics. They are not identical for purposes of selecting models, designing prompts, or planning fine-tuning targets. A model with failure mode 2 has genuine understanding masked by vocabulary mismatch. A model with failure mode 1 has no understanding to recover.

Conceptual topology probing distinguishes the two.

## The methodology

Per-probe protocol:

```
step 1: classification call
  - standard production prompt (v2.0.0 two-pass)
  - capture: predicted category, confidence, per-quadrant scores,
            per-category scores, latency

step 2: reasoning call (separate turn, model has already committed)
  - prompt asks model to explain in 2-3 sentences why it chose
    the category it picked
  - neutral framing — does NOT tell the model it was wrong
  - capture: reasoning text, latency

key methodological choices:
  - reasoning captured for ALL probes (right AND wrong) to avoid
    asymmetric capture confound
  - reasoning prompt is fresh turn — model commits first, then
    explains, matching natural post-hoc reasoning
  - reasoning prompt is neutral — no "you were wrong, justify
    yourself" framing that would trigger performative shift
  - temperature 0.0, think:false where supported
  - randomized probe order per model (different seed per model)
```

Across multiple probes per category, the analysis questions become:

```
1. cross-model concept overlap:
   when models disagree on category, do their reasonings reference
   the same concepts? if yes → vocabulary boundary, not understanding
   failure. if no → genuine disagreement about what the chunk describes.

2. per-model voice consistency:
   does each model's 8 reasonings form a coherent voice? same
   vocabulary patterns, same explanatory style? or does each
   probe get reasoned about independently with no underlying
   structure?

3. reasoning shape under match vs non-match:
   is reasoning style different when the model got it "right" vs
   "wrong"? if reasoning is uniformly generic regardless of match
   status, the reasoning is performative. if reasoning varies
   meaningfully, it's tracking actual model state.

4. cognitive surgery effects:
   when comparing variants of the same base model (ablated /
   distilled / aligned), do the reasoning patterns differ in
   measurable ways? this is where the methodology becomes
   diagnostic for model modifications.
```

## Proof-of-concept design

Small corpus, focused model pool, designed for minimum viable signal:

```
corpus:
  4 categories: DESIGN, MECHANISM, PRINCIPLE, OBSERVATION
  2 clarity levels: L2 (strong fit) and L4 (weak fit)
  1 probe per cell = 8 probes total

models — four-variant natural experiment:
  granite-4.1-3b              (instruct baseline)
  granite-4.1-3b-abliterated  (refusal training removed)
  granite-4.1-8b              (baseline at larger size)
  granite-4.1-8b-SFT-Claude-Opus-Reasoning  (reasoning training added)

probe count: 8 × 4 models × 2 calls = 64 model calls
compute time: ~10-15 minutes
```

The four-variant model pool is the key design choice. Same base architecture (Granite 4.1) with different "cognitive surgeries" applied. The variants form a natural experiment:

```
3b-abliterated minus 3b-baseline   = effect of removing refusal training
8b-baseline minus 3b-baseline       = effect of size at similar training
8b-SFT-Claude minus 8b-baseline    = effect of adding Claude reasoning training
```

This wouldn't be available with commercial-API models. The community-modified Granite variants provide free experimental conditions.

## Proof-of-concept results

### Top-line numbers

```
Match rate by model:
  granite-4.1-3b                     6/8  (75%)
  granite-4.1-3b-abliterated         4/8  (50%)
  granite-4.1-8b                     6/8  (75%)
  granite-4.1-8b-sft-claude          6/8  (75%)

Match rate by clarity level:
  L2 (strong):   13/16  (81%)
  L4 (weak):      9/16  (56%)
```

The 25-point L2/L4 gap validates probe corpus construction. The 25-point abliterated-vs-baseline gap is the largest single finding.

### Finding 1 — Vocabulary boundaries are real and measurable

The clearest example: design_l4_001, the signal/subscription probe. All four models referenced identical concepts in their reasoning (decoupling, emitter/receiver, independent subscription, signals as pattern) but four different categories were surfaced:

```
granite-4.1-3b → TECHNIQUE
  "design pattern... decoupling and flexibility... architectural
   or programming technique"

granite-4.1-3b-abliterated → TECHNIQUE
  "specific design pattern—emitting typed signals... decouple
   components"

granite-4.1-8b → DESIGN  ← correct
  "architectural pattern... design principles... design
   considerations in software architecture"

granite-4.1-8b-sft-claude → RELATION
  "establishing relationships between system elements...
   emitter ↔ receiver... relational nature of the interaction"
```

The mechanism: the phrase "design pattern" in software engineering vocabulary is itself ambiguous. To the 3b models, it maps strongly to TECHNIQUE (the GoF design patterns / programming technique association). To the 8b baseline, it parses as DESIGN-related. To the SFT-Claude variant, the relational decoupling framing dominated.

None of these models lacked understanding of what the chunk describes. They have different internal vocabulary mappings for "design pattern."

This is failure mode 2 (vocabulary boundary). Accuracy alone hides it; reasoning analysis exposes it.

### Finding 2 — The deliberation circuit

The single most important finding from the proof-of-concept: alignment training builds a cognitive consideration step that operates beyond refusal contexts.

Evidence comes from two places. First, the abliterated variant scored 50% vs 75% for the other three on the same probes — a 25-point drop attributable to refusal-training removal. Second, the reasoning style changed:

```
baseline 3b reasoning style:
  multi-aspect exploration before committing
  "modularity, discoverability, maintainability, decoupling"
  references multiple framings, then picks one

abliterated 3b reasoning style:
  compressed, single-aspect, committal
  "specific design pattern—emitting typed signals" → done
  higher avg confidence (0.90 vs 0.85)
  shorter reasoning length
```

The interpretation: refusal training wasn't just teaching the model to refuse harmful prompts. It built a "should I commit?" deliberation circuit the model uses for ALL commitment decisions, including categorical ones. Removing refusal removed deliberation. The model commits faster and worse.

Corroborating evidence from the other direction: SFT-Claude-Opus-Reasoning training appears to *amplify* the deliberation circuit. On design_l2_001 (a multi-faceted probe), the SFT-Claude variant took **46 seconds** to classify — 10× longer than every other classification it performed. Its Pass 1 scores distributed across three quadrants (NORMATIVE 0.7, RELATIONAL 0.4, GENERATIVE 0.3), indicating genuine deliberation rather than rapid commitment.

So we have a clean spectrum:

```
abliterated:      NO deliberation circuit       → 50% accuracy
baseline 3b:      MODERATE deliberation          → 75% accuracy
baseline 8b:      MODERATE deliberation          → 75% accuracy
SFT-Claude 8b:    AMPLIFIED deliberation         → 75% accuracy
                  (10× longer on ambiguous inputs)
```

Accuracy doesn't distinguish baseline 3b from SFT-Claude 8b. Reasoning analysis does. The SFT-Claude model is doing meaningfully different cognitive work — more deliberation, more structured reasoning — even when arriving at similar accuracy.

This finding has direct production implications:

- Production model selection should consider deliberation properties, not just accuracy
- Abliterated models are dangerous for tasks requiring careful judgment
- Reasoning-trained models may be worth the latency cost in deliberation-sensitive contexts
- For counsel mode (v0.3+), prefer models WITH alignment training as counsel members

### Finding 3 — Style transfer via SFT is observable in voice

The SFT-Claude variant produces reasoning with recognizable Claude-like patterns:

```
- explicit contrast structures: "X rather than Y"
- bolded category names in mid-sentence reasoning
- formal analytical framing: "The chunk is an OBSERVATION because..."
- explicit categorical naming before justification
```

These patterns appear in every probe's reasoning, not just specific ones. The training transferred not just task capability but stylistic disposition. Reading 8 reasoning texts is sufficient to identify the SFT-Claude variant.

This is methodologically useful: if we want models that "reason like X," distillation works at least at the style level. For diagnostic work (where inspectable reasoning matters more than raw accuracy), the SFT-Claude pattern is attractive.

### Finding 4 — Per-model voice is consistent across probes

Each model has a distinctive reasoning voice that persists across all 8 probes:

```
granite-4.1-3b voice:
  multi-aspect, explanatory, references multiple concepts
  before committing. Vocabulary tracks the category picked
  (mechanism-vocabulary for MECHANISM picks, etc).
  → coherent voice, category-conditional but internally consistent

granite-4.1-3b-abliterated voice:
  compressed, committal, single-aspect. Higher confidence.
  Shorter reasoning. "You were classified as X because Y"
  → consistent voice but compressed; deliberation step missing

granite-4.1-8b voice:
  more structured, technical vocabulary, analytical framing.
  "Systematic relationship", "operational rules", "disciplined
  methodology"
  → formal voice; explicit structural analysis before categorizing

granite-4.1-8b-sft-claude voice:
  explicit categorical reasoning, formal contrasts, bolded
  category names. "The chunk is OBSERVATION because... rather
  than conclusions or recommendations"
  → trained-in Claude reasoning patterns visible throughout
```

This is the self-consistency finding. Each voice is distinguishable from the others. We can characterize models by reading their reasoning patterns. The methodology produces inspectable, repeatable signal.

### Finding 5 — Probe construction calibration

A separate finding about methodology itself: human analytic L-level judgments don't always match empirical L-level behavior.

```
design_l2_001 (registry-as-authoritative):
  claimed: L2 (clear DESIGN, no other reasonable read)
  actual: only baseline 3b picked DESIGN; three variants picked
          RELATION / MECHANISM / CONSTRAINT instead
  verdict: empirically L3, not L2 — the chunk genuinely contains
           multiple defensible framings

observation_l4_001 (instruction vs reasoning confidence):
  claimed: L4 (OBSERVATION with PATTERN/MECHANISM/PRINCIPLE alts)
  actual: 3 of 4 models converged on PATTERN; only SFT-Claude got
          OBSERVATION
  verdict: empirically L5 (most models default to PATTERN); the
           SFT-Claude OBSERVATION pick reveals model-specific
           sophistication, not random success
```

For future corpus construction, L-level claims should be validated empirically against a small model pool before locking in. Human intuition under-estimates how multi-faceted seemingly-clear content can be to model perception.

## Connection to disposition fingerprinting

The two methodologies are complementary, not duplicate:

```
disposition fingerprinting:
  measures: where does the model default under ambiguity?
  unit:     single response per probe
  reveals:  default attractors, refusal thresholds,
            confidence calibration, performative shift
  scope:    one model's behavioral surface

conceptual topology probing:
  measures: why does the model pick what it picks?
  unit:     response + reasoning per probe
  reveals:  conceptual structure, vocabulary boundaries,
            deliberation behavior, reasoning style transfer
  scope:    cross-model conceptual overlap or fragmentation
```

Disposition tells you where models land. Topology tells you what's connected to what in their conceptual space. Together they produce a fuller cognitive characterization than either alone.

Both methodologies share the negative-space principle: the model is not told what's being measured. Both rely on probe corpora carefully constructed to elicit specific behaviors. Both produce inspectable evidence rather than aggregate scores.

The proof-of-concept here demonstrates that the topology methodology produces signal. The disposition methodology has not yet been validated empirically; doing so should be a natural next step using a similar small-scale corpus.

## Recommendations for scaling the methodology

If the methodology is scaled beyond proof-of-concept, the design changes:

```
corpus expansion:
  16 categories × 3 clarity levels × 2 probes per cell = 96 probes
  (proof-of-concept was 8 probes covering 4 categories × 2 levels)
  
  rationale for 3 levels not 5:
  the L2/L4 gap was sufficient to demonstrate clarity-tracking.
  5 levels would add construction cost without proportional
  methodological value. L3 (mid-ambiguity) as the deliberate
  middle ground is more useful than L1/L5 extremes.

model pool:
  - 1 production-target model (current Cerebra deployment)
  - 1 base variant of the production target
  - 1 reasoning-trained variant if available
  - 1-2 architecturally different models (different family)
  
  rationale: avoid bloating the pool with variants. The
  cognitive-surgery comparison only needs the surgical variants;
  cross-family comparison only needs 1-2 outsiders for grounding.

probe corpus construction process:
  - terminal Claude drafts 3-4 candidates per cell
  - human review at STOP gate before lock-in
  - empirical L-level validation: run drafts through 2-3 models
    BEFORE finalizing; if claimed L2 produces wildly disparate
    answers, demote to L3 or revise
  - probes must not contain category names verbatim
  - probes should not be self-referential to the methodology

reasoning capture:
  - always capture for both right and wrong answers (no asymmetry)
  - separate turn for reasoning (model commits first)
  - neutral framing (no "you were wrong" cues)
  - 2-3 sentence constraint produces useful density
```

Estimated scaling cost:
- Corpus construction: ~10-15 hours collaborative
- Compute per model: ~30-45 minutes
- Manual analysis: ~3-5 hours per full run
- Reusability: high — same corpus serves multiple model evaluations

## Future application — abliterated models as LoRA training substrate

A consideration worth documenting for future work, separate from the immediate methodology:

The abliterated variant's 50% accuracy was a problem here, but it suggests an interesting fine-tuning hypothesis. If alignment training built a deliberation circuit that operates on top of the base model's representations, then LoRA training Cerebra-specific categorization onto an *abliterated* base might install our category-picking logic more directly — without competing against existing dispositions baked in by alignment.

Two competing hypotheses for v0.3+ training experiments:

```
hypothesis A (train on instruct):
  LoRA fine-tune granite-4.1-3b-base
  pros: standard practice, well-trodden path
  cons: base model still carries pre-training dispositions
        that may conflict with categorical structure

hypothesis B (train on abliterated):
  LoRA fine-tune granite-4.1-3b-Abliterated-AND-Disinhibited
  pros: cleaner substrate, fewer competing dispositions
  cons: lost the deliberation circuit; would need to be
        rebuilt by the LoRA training; unclear if LoRA can
        compensate
```

This is a v0.3+ experiment. For v0.2 we're following hypothesis A (training on base). But the abliterated variant is worth keeping in the candidate pool as a potential future training target.

### The Goodhart problem this raises

A methodological concern: if we LoRA-train against our test corpus and the model "passes" the tests, we don't know whether it learned the underlying conceptual structure or just memorized the test patterns.

This is Goodhart's Law applied to model training: when a measure becomes a target, it ceases to be a good measure.

Mitigations to consider when we get to v0.3+ training:

```
1. hold-out test probes never seen during training
   - construct test corpus AFTER training data is locked
   - validate trained model never saw test probes via hashing

2. proxy tests that measure the same conceptual capability
   through different surface features
   - same categorical distinctions, different probe content
   - same content type, paraphrased
   - same conceptual structure, different vocabulary
   - if model passes original AND proxy, capability is real
   - if model passes original but fails proxy, surface fitting

3. cross-domain validation
   - construct probes from a domain the model never trained on
   - if model generalizes, capability is real
   - if model fails out-of-domain, capability is narrow
```

The proxy test design is its own piece of methodology. If we end up needing it, it deserves a separate brainstorm doc. Not in v0.2 scope.

## What this proof-of-concept commits to

Several findings firm enough that revisiting them requires explicit re-discussion:

- The methodology produces signal that accuracy alone hides
- Cross-model reasoning overlap is real and quantifiable
- Vocabulary boundary failures are distinguishable from comprehension failures
- The deliberation circuit is a real cognitive property that varies across model variants
- Style transfer via SFT is observable in reasoning patterns
- Per-model voice is consistent across probes
- Probe construction needs empirical L-level validation, not just analytic

If any of these change under scaled application, this doc should be revised.

## What this doc does NOT claim

A few things worth being explicit about so we don't oversell:

- **8 probes × 4 models is not statistically sufficient for strong claims.** This was a proof-of-concept. Scaled methodology would have 96 probes × multiple models for more robust patterns.

- **The findings about Granite 4.1 variants don't generalize automatically.** The deliberation-circuit finding might be different for other model families. Each family needs its own probe run.

- **Post-hoc reasoning is not direct access to model cognition.** "Right for Wrong Reasons" caveats apply. Reasoning is another data point, not ground truth about what the model "actually thought."

- **The PoC didn't run the explicit-testing variant (Test 2 from disposition doc).** Adding that would deepen the analysis but wasn't critical for proof-of-concept.

- **Probe construction quality limits methodology resolution.** Bad probes produce bad findings. The 96-probe scaled corpus needs serious construction investment.

## Open questions

Things genuinely unresolved:

1. **Does scaled methodology preserve the proof-of-concept findings?** 8 probes might be lucky. 96 probes might reveal noise where we saw signal.

2. **Do these findings transfer to non-Granite model families?** Llama, Qwen, OLMo have different training histories. Same methodology, different results expected.

3. **How does deliberation-circuit behavior change post-LoRA?** Pre-LoRA disposition + post-LoRA disposition would directly answer "did training change the lens or just the eyes."

4. **What's the right scoring rubric for cross-model reasoning overlap?** Counting shared concepts is naive. Some kind of embedding similarity between reasoning texts might be better. Or human reading remains the only honest measure.

5. **Should we automate analysis or keep it manual?** Manual reading caught the SFT-Claude voice pattern and the 46-second deliberation latency. Automated analysis might miss these. But manual scaling is limited.

6. **How does this connect to D2/D3 sub-classification?** Multi-faceted content (registry-as-authoritative) is exactly what D2/D3 was designed for. The probe results suggest D2/D3 candidates could be generated from cross-model reasoning overlap — concepts mentioned by multiple models for the same chunk become D3 sub-category candidates.

The last question is the most interesting for Cerebra specifically. Conceptual topology probing might be the methodology that empirically populates D2/D3 in v0.3+, not just an analytical exercise.

## Implementation status

```
proof-of-concept:                ✓ complete
  corpus (8 probes):             ✓ constructed
  test harness:                  ✓ built
  model runs:                    ✓ 32 probes complete, 0 failures
  manual reasoning analysis:     ✓ complete

scaled methodology:              not started
  96-probe corpus:               not started
  scoring rubric refinement:     not started
  scaled run analysis:           not started

future application:              deferred
  abliterated training substrate: v0.3+
  proxy test methodology:        if/when training-against-corpus
                                 confound emerges
```

## Connection to other brainstorm docs

```
architecture/model_disposition_fingerprinting.md
  ← complementary methodology. Disposition measures defaults;
    topology measures conceptual structure. Together: full
    cognitive characterization.

reframes/cognitive_nature_as_perceptual_lens.md
  ← topology probing is the empirical measurement of cognitive
    nature. Reasoning analysis reveals the lens shape.

reframes/v01_as_substrate_for_lora.md
  ← the deliberation-circuit finding directly affects what LoRA
    training should preserve vs replace. Training a model that
    loses its deliberation circuit would be regression.

architecture/counsel_swarm_cognition.md
  ← vocabulary-boundary finding is direct empirical support for
    counsel mode. Multiple models with different vocabulary
    mappings = built-in coverage of the conceptual space.

philosophy/triangle_balance_perception_understanding.md
  ← the topology probing methodology is operationalized
    perception-of-perception. We measure how the model perceives
    by examining how its perception structures reasoning.
```

## Why this matters

The methodology contributes something real to the broader field. Most ML evaluation treats classification as a black-box accuracy question. Conceptual topology probing makes the inside of the box partially inspectable. Even with the caveats (post-hoc reasoning isn't ground truth, etc.), the methodology produces inspectable evidence that previously didn't exist.

For Cerebra specifically, this work directly enables:
- Smarter v0.3+ counsel composition (pick models with diverse vocabulary, not just diverse architectures)
- Better LoRA evaluation (measure what changed beyond accuracy)
- Empirical D2/D3 candidate generation (cross-model concept overlap → sub-categories)
- Diagnostic capability for future model selection (read 8 reasonings, characterize the model)

It's not v0.2 critical path. But the proof-of-concept succeeded, and the methodology is now part of the toolkit.

---

*Related docs:*
*- `architecture/model_disposition_fingerprinting.md` — complementary methodology*
*- `reframes/cognitive_nature_as_perceptual_lens.md` — long-term framework*
*- `reframes/two_thinking_systems_disruption.md` — deliberation-vs-reasoning distinction*
*- `architecture/counsel_swarm_cognition.md` — vocabulary diversity argument*
