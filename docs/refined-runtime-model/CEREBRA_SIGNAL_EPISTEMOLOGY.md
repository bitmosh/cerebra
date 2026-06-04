# Cerebra — Signal Epistemology

## 1. Purpose

This document defines the epistemological foundation of Cerebra's signal pipeline.

Signals are not implementation artifacts. They are the projection of a coherent cognitive epistemology into measurable axes. If the underlying epistemology is sound, the signals fall out of it naturally and the system measures what actually matters.

The six core signals defined here derive from threads that converge across philosophical traditions — analytic logic, phenomenology, Buddhist epistemology, Sufi tradition, scholastic precision, pragmatist criteria, and the practical reality of how language models succeed and fail. The convergence is not coincidence. These are the conditions under which thought can be reliable.

This document is the foundation for `CEREBRA_PREDICTION_AND_EVALUATION.md`, the seed of the eventual `CEREBRA_PHILOSOPHY.md`, and the source of truth for which signals the cycle runtime evaluates.

---

## 2. Core Doctrine

Signal epistemology should be:

```text
foundationally grounded (in convergent epistemological tradition)
operationally specific (each signal maps to checkable moves)
failure-mode-aware (each signal corresponds to a known failure mode)
component-preserving (do not collapse signals into a single opaque score)
calibration-auditable
human-defensible (we can explain why each signal exists)
LLM-failure-mode-mapping
```

The signal pipeline's job is to measure thinking quality across the axes that the perennial threads identify as load-bearing. Not more axes. Not fewer.

---

## 3. The Six Perennial Threads

Six threads emerged from analyzing what philosophical and contemplative traditions agree on as markers of reliable thought. Each thread shows up in multiple independent traditions because it captures a real condition for thinking, not a culturally specific preference.

### 3.1 Thread 1 — Internal Consistency

```text
Tradition:      Aristotle's non-contradiction principle
                Buddhist logic's catuṣkoṭi avoidance
                Critical thinking's "does this argument hold together"
LLM reality:    coherence within and across outputs
Failure mode:   self-contradiction
```

Thought that contradicts itself is broken regardless of which side of the contradiction is true.

### 3.2 Thread 2 — Grounding in Evidence or Experience

```text
Tradition:      empiricism's foundation
                phenomenology's "return to the things themselves"
                Sufi emphasis on direct knowing vs hearsay
                critical thinking's "what's the evidence"
LLM reality:    hallucination is the failure of this thread
Failure mode:   floating free of any anchor
```

Thought disconnected from evidence or experience is suspect even when fluent.

### 3.3 Thread 3 — Productive Tension With What Came Before

```text
Tradition:      Hegel's dialectic
                Zen's koans
                scientific paradigm shifts
                critical thinking's "what would change my mind"
LLM reality:    novelty without sycophancy
Failure mode:   pure repetition on one extreme, pure contradiction on the other
```

Thought that only repeats is dead; thought that only contradicts is destructive. Productive thinking exists in the tension.

### 3.4 Thread 4 — Fit to Purpose / Serving the Question

```text
Tradition:      Aristotle's phronesis (practical wisdom)
                Buddhist skillful means (upaya)
                pragmatist "what difference does it make"
                critical thinking's "is this responsive"
LLM reality:    relevance to the user's actual need
Failure mode:   technically correct but unhelpful
```

Thought disconnected from the question being asked has limited value regardless of its other qualities.

### 3.5 Thread 5 — Clarity of Distinction

```text
Tradition:      scholastic precision
                logical positivism's verification
                Buddhist analytical meditation
                critical thinking's "define your terms"
LLM reality:    specificity, avoiding mush
Failure mode:   sloppy collapsing of distinctions that should be kept
```

Thought that blurs distinctions it should keep produces conclusions that don't survive examination.

### 3.6 Thread 6 — Awareness of Own Limits

```text
Tradition:      Socratic "I know that I know nothing"
                apophatic theology
                Gödel's incompleteness
                Buddhist "don't mistake the finger for the moon"
                critical thinking's epistemic humility
LLM reality:    calibrated confidence; knowing what you don't know
Failure mode:   overclaiming
```

Thought claiming more than it has earned is dangerous in proportion to how confidently it claims.

---

## 4. The Six Core Signals

The six threads project directly onto six measurable signals.

### 4.1 COHERENCE

Maps to Thread 1 (Internal Consistency).

```text
Question:     Does this output hold together internally?
Checks:       contradiction detection
              equivocation detection
              non-sequitur detection
              hidden premise surfacing
              circular reasoning detection
Range:        0.0 - 1.0
Default weight: 0.18
```

### 4.2 GROUNDEDNESS

Maps to Thread 2 (Grounding in Evidence).

```text
Question:     Is this output anchored in evidence or experience?
Checks:       source quality assessment
              source quantity assessment
              source recency assessment
              derivation chain traceability
              hallucination detection (claims unsupported by sources)
Range:        0.0 - 1.0
Default weight: 0.18

Subsumes the old: retrieval_quality, source_support
```

### 4.3 GENERATIVITY

Maps to Thread 3 (Productive Tension).

```text
Question:     Does this output advance understanding?
Checks:       genuine novelty vs sycophantic agreement
              productive tension vs destructive contradiction
              dialectic advance vs flat repetition
              insight emergence
              progress against prior cycle states
Range:        0.0 - 1.0
Default weight: 0.12

Subsumes the old: novelty, surprise, progress_delta
```

### 4.4 RELEVANCE

Maps to Thread 4 (Fit to Purpose).

```text
Question:     Does this output serve what was actually asked?
Checks:       direct goal alignment
              context fit
              user-need responsiveness
              tangent detection
              project-scope respect
Range:        0.0 - 1.0
Default weight: 0.22

Subsumes the old: goal_alignment, context_fit, usefulness
```

### 4.5 PRECISION

Maps to Thread 5 (Clarity of Distinction).

```text
Question:     Does this output keep distinct what should be kept distinct?
Checks:       vague term detection
              undefined reference detection
              ambiguous pronoun detection
              weasel word detection
              scope creep within a single output
Range:        0.0 - 1.0
Default weight: 0.12

Subsumes the old: specificity
```

### 4.6 EPISTEMIC HUMILITY

Maps to Thread 6 (Awareness of Own Limits).

```text
Question:     Does this output appropriately bound its own claims?
Checks:       explicit uncertainty markers
              acknowledged scope limits
              distinguished known from unknown
              calibrated qualifier usage
              avoidance of overclaiming
Range:        0.0 - 1.0
Default weight: 0.18

NEW. No equivalent in the old 11-signal set.
```

**The new addition is load-bearing.** Epistemic humility is not in the old set but is the perennial thread most directly relevant to AI systems. A system that scores its own outputs on whether they know what they don't know is qualitatively different from a system that doesn't. This is the signal that, more than any other, distinguishes a memory system that thinks from a memory system that asserts.

---

## 5. The Triangulating Multipliers

Two metadata signals do not enter the weighted composite. They multiply the composite to produce the final reward.

### 5.1 CONFIDENCE

```text
Question:     How strongly does the system assert these signal scores?
Operates as:  multiplier in reward triangulation
Range:        0.0 - 1.0
```

Confidence is the system's claim about its own evaluation, not about the output. A confident evaluation of a poor output is still a poor reward. A low-confidence evaluation of a great output is dampened reward because the system doesn't trust its own measurement.

### 5.2 SIGNAL_STRENGTH

```text
Question:     How rich is the underlying data?
Operates as:  multiplier in reward triangulation
Range:        0.0 - 1.0
```

Signal strength reflects input quality, not output quality. A high-quality evaluation done on thin input data is still uncertain.

### 5.3 Confidence vs Epistemic Humility

These are related but distinct.

```text
CONFIDENCE:         the system's claim about its scoring
                    "I am 0.84 confident in these signal scores"

EPISTEMIC HUMILITY: the output's claim about its own limits
                    "this output appropriately bounds what it knows"
```

A high-confidence score on epistemic humility means: "the system is confident that this output knows what it doesn't know." Both can vary independently.

---

## 6. The Composition Formula

```text
composite = Σ (signal_i × weight_i)  for i in {coherence, groundedness, generativity,
                                                 relevance, precision, epistemic_humility}
                                     where Σ weight_i = 1.0

reward = composite × confidence × signal_strength
             range typically [0, 1.0] with occasional overshoot to ~1.2
```

Default weights (sum to 1.00):

```text
COHERENCE           0.18
GROUNDEDNESS        0.18
GENERATIVITY        0.12
RELEVANCE           0.22
PRECISION           0.12
EPISTEMIC HUMILITY  0.18
                    ----
                    1.00
```

Per-cycle configs override defaults. Examples:

```text
Code-review cycle:    down-weight GENERATIVITY (we're checking correctness, not
                      inventing ideas), up-weight COHERENCE and PRECISION

Brainstorming cycle:  up-weight GENERATIVITY, temporarily down-weight PRECISION
                      and RELEVANCE (broad exploration tolerated)

Decision-support cycle: up-weight EPISTEMIC HUMILITY and GROUNDEDNESS, down-weight
                        GENERATIVITY (we want reliable, not novel)

Critique cycle:       up-weight COHERENCE and PRECISION (we're stress-testing),
                      keep EPISTEMIC HUMILITY high
```

---

## 7. LLM Failure Mode Mapping

Each signal corresponds to a known LLM failure mode. This is the alignment check between the epistemological foundation and the practical engineering reality.

```text
COHERENCE          ⟷  self-contradiction within output
GROUNDEDNESS       ⟷  hallucination
GENERATIVITY       ⟷  sycophancy / mode collapse / repetition
RELEVANCE          ⟷  drift / tangent generation
PRECISION          ⟷  mush / vague language
EPISTEMIC HUMILITY ⟷  overclaiming / false confidence
```

The mapping is one-to-one. Six signals, six failure modes. This is not coincidence — both the perennial threads and LLM failure modes are describing the same underlying conditions for reliable thought, viewed from different angles.

This mapping is the engineering payoff of the epistemological grounding. When the system detects a signal regression, the regression points to a specific failure mode the cycle can address.

---

## 8. The Operational Layer

The six signals are the *axes*. The operational moves underneath them are the *prompts*.

Each signal has a checklist of critical-thinking moves that the LLM runs when scoring. The checklist is the prompt's structure; the score is the output.

### Example: COHERENCE checklist

```text
For this output, evaluate:
  1. Does any claim contradict any other claim?
  2. Are any terms used with different meanings in different places?
  3. Do conclusions follow from their stated premises?
  4. Are any premises hidden that the argument depends on?
  5. Does the reasoning loop back to assume what it's trying to prove?

For each item, identify specific lines and rate severity 0-3.
Aggregate to a 0-1 COHERENCE score.
```

### Example: GROUNDEDNESS checklist

```text
For this output, evaluate:
  1. Which claims have explicit source backing?
  2. For unsourced claims, are they common knowledge or are they assertion?
  3. Are sources cited recent enough to be relevant?
  4. Is the derivation chain from source to claim traceable?
  5. Are any claims confidently asserted that the sources don't support?

For each item, identify specific lines and rate severity 0-3.
Aggregate to a 0-1 GROUNDEDNESS score.
```

Each checklist becomes a prompt template. Templates are versioned (`coherence_check_v3`) so calibration audits can compare scores across template versions.

---

## 9. Multi-Prompt Triangulation

For high-stakes evaluation, signals are scored via multiple prompts that triangulate.

The six signals group naturally into three pairs by family:

```text
Structural family:    COHERENCE + PRECISION
                      (both about internal structure of the output)

Grounding family:     GROUNDEDNESS + EPISTEMIC HUMILITY
                      (both about the output's relationship to truth/uncertainty)

Service family:       RELEVANCE + GENERATIVITY
                      (both about the output's contribution to the task)
```

A triangulated evaluation runs three prompts, one per family, and compares.

```text
Signals where all three prompts agree (within tolerance): high confidence
Signals where prompts disagree: low confidence, flag for review
Signals where a prompt is wildly out of range: that prompt may be miscalibrated
```

Cost is 3x a single-prompt evaluation. Apply where stakes justify it:

```text
Always:    user-pinned content evaluation
Always:    memories being promoted from episodic to semantic
Always:    terminal-group clutch decisions
Optional:  routine cycle steps
```

---

## 10. Continental Modifier (v0.2+ direction)

The perennial threads above derive from analytic and contemplative traditions. Continental philosophy adds a thread the analytic tradition doesn't quite capture: **embodied and situated knowing**.

For Cerebra, this maps to: the *context* a memory was formed in is part of what the memory means. The same proposition formed in different contexts may mean different things.

This is not a 7th signal in v0.1. It is a signal *modifier* that may emerge in v0.2+ as:

```text
CONTEXTUAL_SITUATEDNESS  not weighted in composite
                          adjusts interpretation of other signals
                          "this output is high-relevance in context X but
                           free-floating outside it"
```

The modifier doesn't replace any signal; it qualifies them. Worth keeping the architectural seam available even if not implemented.

---

## 11. Archetypal Modality (v0.3+ direction)

The mystical traditions across cultures distinguish kinds of knowing — discursive, apprehensive, participative. They are not the same and don't reduce to each other.

For Cerebra, this maps to: the SKU's D9 modality digit can eventually encode not just *what form* the memory takes (text/code/graph) but *what kind of knowing* it represents:

```text
Discursive:     "X is the case because Y"   (propositional)
Apprehensive:   "I noticed Z about this"     (pattern recognition)
Participative:  "working in this domain feels like..."  (immersive)
```

This is v0.3+ territory. It represents the system genuinely modeling different cognitive modes rather than just different content types. The architectural seam should be preserved: D9's value space should not be exhausted by content-type categories alone.

---

## 12. Calibration

Signals are calibrated over time. The consolidation engine periodically reviews:

```text
predicted signal score vs actual signal score (when measurable)
per-signal systematic bias
per-signal variance vs claimed confidence
cross-prompt agreement in triangulated evaluations
```

Calibration deltas adjust per-signal scoring formulas. This is the prediction-error feedback loop applied to the signal pipeline itself.

Per-signal calibration is stored as scoring weight adjustments:

```text
signal_calibration[COHERENCE] = {
  systematic_bias: -0.04,     # tends to under-score; add 0.04 to raw
  variance_adjustment: 1.1,   # claimed-confidence is 10% optimistic
  last_calibrated_at: timestamp
}
```

Calibration is incremental. Single events do not change weights. Patterns across multiple cycles do.

---

## 13. Integration With Existing Components

**Prediction and Evaluation (`CEREBRA_PREDICTION_AND_EVALUATION.md`):** this doc replaces §8 of that doc with the six-signal architecture. The composition formula and threshold structures remain compatible.

**Cycle Runtime (`CEREBRA_COGNITIVE_RUNTIME.md`):** the cycle config's `metrics:` field uses the six-signal vocabulary. Clutch rules can reference any signal in their guard expressions.

**Catalyst (`CEREBRA_CATALYST.md`):** the catalyst's `reward` input is the triangulated composite. Strategy selection learns which strategies improve which signals.

**Consolidation Engine (`CEREBRA_CONSOLIDATION_ENGINE.md`):** calibration audits run during consolidation. Calibration deltas update signal scoring formulas.

**Truth Tower (`CEREBRA_TRUTH_TOWER.md`):** each tier has implicit signal priorities — T1 evidence cares most about GROUNDEDNESS, T3 insights about COHERENCE and GENERATIVITY, T4 hypotheses about EPISTEMIC HUMILITY, T5 goal about RELEVANCE.

**SKU Addressing (`CEREBRA_SKU_ADDRESSING.md`):** the SKU's D6 novelty band is a coarse summary of GENERATIVITY. High-GENERATIVITY memories cluster at the "pioneering" and "surprising" bands.

**Drift Fixes (`CEREBRA_DRIFT_FIXES_v8.1.md`):** §4 of the drift fix doc is superseded by this doc. The 11-signal list and weights there are deprecated.

---

## 14. MVP Scope

Cerebra v0.1 should implement:

```text
All six signals as the cycle's evaluation vocabulary
Composition formula with confidence and signal_strength multipliers
Default weights per the table in §6
Per-cycle weight override via cycle config
Single-prompt evaluation per signal (triangulation deferred to v0.2)
EPISTEMIC HUMILITY scored even if scoring is simple (presence of qualifiers)
LLM failure mode mapping logged when signals score low
```

Cerebra v0.2 adds:

```text
Multi-prompt triangulation for high-stakes evaluations
Calibration audits via consolidation engine
Per-cycle config templates that pre-set weights for known cycle types
```

Cerebra v0.3+:

```text
Continental modifier (CONTEXTUAL_SITUATEDNESS as signal qualifier)
Archetypal modality in SKU D9
Cross-cycle signal learning (calibration that transfers between cycle configs)
```

---

## 15. Testing Requirements

Signal epistemology tests should cover:

```text
each signal has a checklist prompt that produces scores in [0, 1]
composition formula respects weight sum constraint
weights sum to 1.0 ± 0.05 in valid configs
EPISTEMIC HUMILITY recognizes uncertainty markers
EPISTEMIC HUMILITY penalizes overclaiming language
COHERENCE detects deliberate contradictions in test fixtures
GROUNDEDNESS rewards source-cited content over unsourced
GENERATIVITY distinguishes novelty from sycophancy
RELEVANCE rewards on-topic over fluent-tangent
PRECISION rewards specific over vague
triangulation produces three scores per family for high-stakes content
calibration audit recognizes systematic bias
LLM failure mode logs fire when corresponding signal drops below threshold
```

---

## 16. Signal Epistemology Doctrine

A memory system that thinks must measure thinking quality. That requires knowing what thinking quality is.

The convergence across philosophical and contemplative traditions on six perennial threads — consistency, grounding, productive tension, fit to purpose, clarity, and humility — is the strongest available answer to that question. Each tradition arrived at these threads independently because they describe real conditions for reliable thought, not cultural preferences.

The six signals derived from these threads have three useful properties:

```text
they are foundationally grounded
they map one-to-one onto known LLM failure modes
they are operationally specific enough to score
```

This is what distinguishes Cerebra's signal pipeline from systems that pick metrics arbitrarily. Other systems measure what's easy to measure. Cerebra measures what the traditions identify as load-bearing for reliable thinking.

The addition of EPISTEMIC HUMILITY as a first-class signal is the most consequential single decision in the signal architecture. It is the signal that, more than any other, distinguishes a memory system that earns trust from one that asserts it.

This is the epistemological foundation. The implementation flows from here.
