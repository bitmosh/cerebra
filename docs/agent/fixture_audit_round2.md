# Second Fixture Audit — 4 Consensus-Failure Fixtures

**Date:** 2026-06-06  
**Prompt:** `docs/workflows/fixture_audit_round2_prompt.md`  
**Coverage:** 13 models (Round 1 × 11 + Round 2 × 2), run-1 predictions, strict scoring  
**Reference:** `CEREBRA_SKU_ADDRESSING.md` §4 category definitions

---

## Preliminary note: prompt content mix-up

The audit prompt has the fixture content for `clear_07` and `hard_07` swapped — it
describes `clear_07` as the approval gate text and `hard_07` as the "Phase 2 scope: assign
D1, D4..." text. The fixture file is ground truth. Correct content per `sku_fixtures.py`:

- **clear_07** → sku_assignments table schema
- **hard_07** → approval gate convention/workflow description
- **hard_09** → Phase 2 scope: assign D1, D4, D9, D10... (not audited here)

All analysis below uses the fixture file content, not the prompt's description.

---

## Fixture 1 — clear_07 (current label: DESIGN)

**Content:**
> "The sku_assignments table stores: assignment_id (PK), record_id (FK), sku_address, d1
> through d10 digit columns, raw_scores_json, classifier_version, prompt_version,
> subcategory_strategy_version, model_string, latency_ms."

**Prediction distribution (13 models):**

| Predicted | Count | Models |
|-----------|:-----:|--------|
| OBSERVATION | 10 | qwen4b, qwen2b, qwen0.8b, llama31, olmo3, granite4-tiny, granite4-micro, smollm3, hermes3, granite41-3b |
| PHENOMENON | 2 | qwen9b, granite41-8b |
| MECHANISM | 1 | mistral-nemo |

Current label DESIGN: **0/13** correct. No model picked DESIGN.

**Analysis:**

DESIGN is defined as "intentional structure; choices made for purposes." A table schema is
unambiguously a design artifact — the developer chose which columns to include and why. The
fixture notes correctly identify this as "schema definition — intentional structure."

However, the text surface is "X stores: field1, field2, field3..." This framing reads as a
factual declaration of what exists, not as a statement of design intent. The word "stores"
and the bare enumeration give the text the character of a reference fact (OBSERVATION: direct
data; raw information about a system) rather than an intentional design record.

Compare to `hard_14`, which is also a schema labeled DESIGN: "Deviation log entry format:
state what the plan said, what was shipped instead, why it deviated..." The word "format:"
explicitly signals designed structure. `clear_07` lacks this signal — "stores:" reads as
descriptive, not prescriptive.

The schema IS a design; the text just doesn't say so in a way models recognize.

**Verdict: MARK_AMBIGUOUS**

Primary: DESIGN. Add `ambiguous_with=OBSERVATION`.

OBSERVATION is defensible: "the sku_assignments table stores X" is also a statement of fact
about the system's data model. Models reading the enumeration as "here is what this table
contains" are not wrong — they're seeing the observational surface of a design artifact.

**After change:** 10/13 models get 0.5 credit (those predicting OBSERVATION). 2/13 get 0
(PHENOMENON). 1/13 gets 0 (MECHANISM).

---

## Fixture 2 — clear_11 (current label: EVENT)

**Content:**
> "Phase 0 complete at commit 5747c7e on 2026-06-04. 88 tests passed. Repository
> initialized, governance loaded, first vault created successfully."

**Prediction distribution (13 models):**

| Predicted | Count | Models |
|-----------|:-----:|--------|
| OBSERVATION | 12 | qwen9b, qwen4b, qwen2b, llama31, olmo3, granite4-tiny, granite4-micro, smollm3, hermes3, mistral-nemo, granite41-3b, granite41-8b |
| PHENOMENON | 1 | qwen0.8b |

Current label EVENT: **0/13** correct. 12/13 picked OBSERVATION — the strongest consensus
of any fixture across both rounds.

**Analysis:**

EVENT is defined as "things that happened in time; moments; situated occurrences."
OBSERVATION is defined as "direct sensory or measurement data; raw events."

"Phase 0 complete at commit 5747c7e on 2026-06-04" is unambiguously an event anchored in
time. It happened at a specific commit on a specific date. This fits EVENT exactly.

But sentences 2 and 3 are measurement data: "88 tests passed" is a count; "Repository
initialized, governance loaded, first vault created successfully" is a status readout. These
read as the *evidence* or *record* of the event — not the event itself.

The surface majority of the text is observational: 2 of 3 sentences are measurements and
state records. Only the first sentence's framing ("Phase 0 complete at commit X on date Y")
makes this clearly an EVENT.

12/13 models — including all the strongest performers — read this as OBSERVATION. The
measurement content dominates the surface even though the time-anchoring of sentence 1 is
clear EVENT framing. Both readings are defensible.

**Verdict: MARK_AMBIGUOUS**

Primary: EVENT. Add `ambiguous_with=OBSERVATION`.

The time-anchored "Phase 0 complete at commit X on 2026-06-04" framing makes EVENT the
primary. But the measurement content ("88 tests passed") makes OBSERVATION a legitimate
alternative — reading the chunk as "here is the data recorded at Phase 0 completion" rather
than "here is the Phase 0 completion moment itself."

**After change:** 12/13 models get 0.5 credit (those predicting OBSERVATION). 1/13 gets 0
(PHENOMENON).

---

## Fixture 3 — hard_02 (current label: MECHANISM, ambiguous_with: DESIGN)

**Content:**
> "The leeway network inverts prohibition models. Instead of specifying what is forbidden, it
> specifies what is permitted under what conditions. Everything outside the network is
> implicitly disallowed."

**Prediction distribution (13 models):**

| Predicted | Count | Credit (current) |
|-----------|:-----:|:----------------:|
| PRINCIPLE | 7 | 0 |
| CONSTRAINT | 3 | 0 |
| DESIGN | 1 | **0.5** |
| JUDGMENT | 1 | 0 |
| PHENOMENON | 1 | 0 |
| MECHANISM | 0 | — |

Current label MECHANISM: **0/13** correct.  
Current `ambiguous_with` DESIGN: **1/13** (0.5 credit).

**Analysis:**

Current label MECHANISM = "how something works; causal chains; process understanding."
Current ambiguous_with DESIGN = "intentional structure; choices made for purposes."

The first sentence — "The leeway network *inverts* prohibition models" — is architectural
design language. "Inverts" signals a deliberate decision about how to approach the problem;
"instead of X, it does Y" is a design decision framing, not a causal-chain description.

Sentences 2 and 3 describe how the design plays out operationally ("specifies what is
permitted under what conditions... everything outside is implicitly disallowed"). These mix
mechanistic description with normative implication.

The problem is the current labeling:
- **MECHANISM gets 0 votes.** The text doesn't read as a causal chain.
- **DESIGN gets 1 vote.** Despite sentence 1 being classic design-decision language.
- **PRINCIPLE + CONSTRAINT together get 10 votes.** The phrase "everything outside the
  network is implicitly disallowed" reads as a rule — a normative claim about what the
  system prohibits.

The current `ambiguous_with=DESIGN` is wrong in two ways: (1) DESIGN is what the first
sentence most directly describes, making it a better *primary*; (2) the models' actual
defensible alternative is PRINCIPLE (7 models), not DESIGN (1 model).

The text structure:
- Sentence 1: "inverts prohibition models" → design decision (DESIGN)
- Sentence 2: "specifies what is permitted" → operational rule (PRINCIPLE / MECHANISM)
- Sentence 3: "implicitly disallowed" → normative constraint (PRINCIPLE / CONSTRAINT)

The dominant character is the design decision (sentence 1) with normative implications
(sentences 2-3). DESIGN is the better primary; PRINCIPLE is the actual defensible alternative.

**Verdict: RELABEL**

Swap primary from MECHANISM to **DESIGN**. Change `ambiguous_with` from DESIGN to
**PRINCIPLE**.

"Inverts prohibition models" is a design-decision statement. The text describes an
architectural choice (permit-list over deny-list) and its normative implications. DESIGN
primary is more accurate. PRINCIPLE as `ambiguous_with` reflects the 7 models reading the
normative governance framing ("everything outside is implicitly disallowed") as a rule/doctrine.

**After change:**
- DESIGN (1 model, smollm3): upgrades from 0.5 to **1.0** credit
- PRINCIPLE (7 models): gets **0.5** credit
- CONSTRAINT (3 models), JUDGMENT (1), PHENOMENON (1): remain at 0

---

## Fixture 4 — hard_07 (current label: DESIGN, ambiguous_with: PRINCIPLE)

**Content:**
> "The approval gate is a workflow convention, not a CLI feature. bumper renders and traces,
> and you (or your agent) post a dry-run sample for approval before the live bump."

**Prediction distribution (13 models):**

| Predicted | Count | Credit (current) |
|-----------|:-----:|:----------------:|
| TECHNIQUE | 5 | 0 |
| MECHANISM | 2 | 0 |
| PHENOMENON | 2 | 0 |
| PRINCIPLE | 1 | **0.5** |
| OBSERVATION | 1 | 0 |
| GOAL | 1 | 0 |
| AGENT | 1 | 0 |

Current label DESIGN: **0/13** correct.  
Current `ambiguous_with` PRINCIPLE: **1/13** (0.5 credit).

**Analysis:**

DESIGN = "intentional structure; choices made for purposes."
TECHNIQUE = "procedural knowledge; how-to; methods; craft."
PRINCIPLE = "rules, doctrines, ethics; 'should' statements."

Sentence 1 — "The approval gate is a workflow *convention*, not a *CLI feature*" — is design
language. The "is X, not Y" construction signals a deliberate classification/architectural
decision: the developer chose to implement the gate as a convention rather than a CLI
feature. This is DESIGN.

Sentence 2 — "bumper renders and traces, and you (or your agent) post a dry-run sample for
approval before the live bump" — is procedural. It describes steps to follow: render, trace,
post dry-run, get approval, then bump. This reads as TECHNIQUE (how to use the gate) or
MECHANISM (how the gate operates).

5/13 models (granite4-micro, hermes3, mistral-nemo, granite41-3b, granite41-8b) pick
TECHNIQUE — specifically the stronger models. The procedural second sentence dominates
their read. Only 1/13 picks PRINCIPLE (the current `ambiguous_with`).

DESIGN as primary is correct — sentence 1 is a design decision statement. But the
`ambiguous_with` is mis-aimed. PRINCIPLE gets 1 vote; TECHNIQUE gets 5. The actual
defensible alternative is TECHNIQUE: the procedural second sentence is substantial enough
that reading the whole as "how the approval workflow works" is legitimate.

**Verdict: FIX ambiguous_with only**

Keep primary **DESIGN**. Change `ambiguous_with` from PRINCIPLE to **TECHNIQUE**.

The "is X, not Y" framing of sentence 1 keeps DESIGN as correct. But the procedural
sentence 2 makes TECHNIQUE the genuine defensible alternative — the chunk reads partly as
"here is how to do the approval workflow." PRINCIPLE is not meaningfully defensible compared
to TECHNIQUE given the text.

**After change:** 5/13 models (TECHNIQUE) get 0.5 credit. The 1 PRINCIPLE prediction
loses its 0.5 credit.

---

## Summary

| Fixture | Current label | Verdict | Change |
|---------|--------------|---------|--------|
| clear_07 | DESIGN | MARK_AMBIGUOUS | add `ambiguous_with=OBSERVATION` |
| clear_11 | EVENT | MARK_AMBIGUOUS | add `ambiguous_with=OBSERVATION` |
| hard_02 | MECHANISM / `ambiguous_with=DESIGN` | RELABEL | primary → DESIGN, `ambiguous_with` → PRINCIPLE |
| hard_07 | DESIGN / `ambiguous_with=PRINCIPLE` | FIX ambiguous_with | keep DESIGN, `ambiguous_with` → TECHNIQUE |

**Counts:** 0 KEEP / 2 MARK_AMBIGUOUS / 1 RELABEL / 1 FIX-ambiguous_with

### Cross-fixture pattern

All 4 failures share the same root: **surface framing overriding semantic intent**. In each
case, the latter part of the chunk text produces a strong surface signal that overrides the
category the chunk primarily represents:

- **clear_07**: "X stores: field1, field2..." → observational enumeration surface over a schema design
- **clear_11**: "88 tests passed" → measurement surface over a time-anchored event
- **hard_02**: "everything outside is implicitly disallowed" → normative surface over a design decision
- **hard_07**: "bumper renders and traces, and you post..." → procedural surface over a design choice

In 3 of 4 cases, the second sentence is the misleading element. First sentences are unambiguous
for the intended label; the remainder tilts the read. This is a calibration-set construction
issue, not a taxonomy issue — the categories are correct, but the fixtures would benefit from
more uniform framing or from moving these content types to explicit ambiguous status.

---

## Implied accuracy ceiling after all 4 changes

Per-model improvement from applying all 4 verdicts (partial-credit gains only):

| Model | Baseline | +clear_07 | +clear_11 | +hard_02 | +hard_07 | New partial |
|-------|:--------:|:---------:|:---------:|:--------:|:--------:|:-----------:|
| granite41-3b | 58% | +0.5 (OBS) | +0.5 (OBS) | +0.5 (PRIN) | +0.5 (TECH) | **65%** |
| granite41-8b | 57% | 0 (PHEN) | +0.5 (OBS) | +0.5 (PRIN) | +0.5 (TECH) | **62%** |
| granite4-micro | 53% | +0.5 (OBS) | +0.5 (OBS) | +0.5 (PRIN) | +0.5 (TECH) | **60%** |
| qwen3.5-9b | 58% | 0 (PHEN) | +0.5 (OBS) | 0 (CONS) | 0 (MECH) | **60%** |
| qwen3.5-4b | 55% | +0.5 (OBS) | +0.5 (OBS) | 0 (JUDG) | 0 (GOAL) | **58%** |
| hermes3 | 37% | +0.5 (OBS) | +0.5 (OBS) | +0.5 (PRIN) | +0.5 (TECH) | **43%** |
| mistral-nemo | 43% | 0 (MECH) | +0.5 (OBS) | 0 (CONS) | +0.5 (TECH) | **47%** |

After applying all 4 changes, **the 70% gate remains unreachable without fine-tuning.**
Best-case ceiling for the top performers is ~65% (granite41-3b). The calibration set will
be more honest — fixtures that were genuine label problems no longer drag down scores on
defensible alternative choices — but the fundamental finding from the consultation stands:
the 16-category taxonomy requires task-specific training to exceed the 70% threshold.

---

## Recommendation

Apply all 4 changes to `sku_fixtures.py`. In order of impact:

1. **hard_02** (RELABEL): highest structural correction — current primary (MECHANISM) gets 0
   votes; proposed primary (DESIGN) is the first sentence's literal meaning. Also fixes the
   `ambiguous_with` to reflect where models actually land.

2. **clear_07** (MARK_AMBIGUOUS): 10/13 models picking OBSERVATION are not wrong — they're
   reading the observational surface of a design schema. Award partial credit.

3. **clear_11** (MARK_AMBIGUOUS): 12/13 models agree on OBSERVATION. The measurement content
   ("88 tests passed") is substantial enough that OBSERVATION deserves partial credit.

4. **hard_07** (FIX ambiguous_with): lower priority — DESIGN primary is correct, only the
   `ambiguous_with` is mis-aimed. Changes partial-credit eligibility from 1 model (PRINCIPLE)
   to 5 models (TECHNIQUE).

Do NOT modify `sku_fixtures.py` in this pass. User decides which changes to apply.
