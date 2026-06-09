# Brainstorm Docs Update — Post-v0.1.0

Light edits to three brainstorm docs in `docs/brainstorm/` to reflect the current state after Round 2 calibration, Round 2 fixture audit, and Phase 2 close-out shipping v0.1.0.

## Context

The brainstorm directory was created during Phase 2 capturing architectural thinking that emerged. Several docs reference specific models (OLMo 3, Granite 4 Micro) as candidates based on Round 1 data. Subsequent work added:

1. Round 2 calibration data identifying Granite 4.1 3B as the substrate
2. The fact that we've been running the instruct variant in production all along (not base)
3. Empirical disagreement-as-signal data from 13-model calibration
4. v0.1.0 actually shipped — substrate-for-LoRA reframe is now historical fact, not just theory

The docs don't need major rewrites — just specific factual updates and the addition of one new finding (per-model failure-mode diversity).

## Reference materials

Read before editing:

- `docs/agent/multi_model_comparison.md` — Round 1 results
- `docs/agent/multi_model_comparison_round2.md` — Round 2 results
- `docs/agent/fixture_audit_round2.md` — Round 2 fixture audit
- `docs/agent/granite41_3b_validation.md` — production substrate validation
- `docs/agent/deviations/v0.1.0.md` — full v0.1.0 close-out narrative
- `docs/brainstorm/` — the docs to update

## Docs to update

### 1. `docs/brainstorm/reframes/v01_as_substrate_for_lora.md`

The reframe is no longer hypothetical — v0.1.0 shipped at 65% partial-credit accuracy on Granite 4.1 3B with 745-record backfill complete. The doc should reflect this with updates.

Specific changes:

**Update model references:**
- Replace "OLMo 3 7B as the LoRA target" with "Granite 4.1 3B base as the LoRA target"
- Reasoning: Round 2 calibration data invalidated OLMo 3 as a candidate (45% accuracy, 65s/call latency, uncontrollable chain-of-thought). Granite 4.1 3B base scored 58% partial baseline accuracy with 73% Pass 1 quadrant accuracy — best of any tested model
- Note OLMo 3 remains as a secondary candidate / fallback for model-flow capabilities

**Add a "What actually shipped" section near the end (before the "Honest framing" section):**

```markdown
## What actually shipped in v0.1.0

The reframe became historical fact on 2026-06-06. Phase 2 close-out:

- Production substrate: Granite 4.1 3B instruct (Unsloth GGUF)
- Calibration: 65% partial-credit accuracy (53% strict)
- Backfill: 745 records classified, 0 parse failures, 28.3 minutes total
- Perfect determinism: temp=0.0, same chunk → same SKU on re-run
- Gate criterion documented as substrate-for-LoRA, not raw accuracy

The 745 labeled records become the v0.2 LoRA training corpus. The substrate-for-LoRA argument is no longer a planning hypothesis; it's the working architecture.

One discovery worth noting: the production model is the **instruct** variant of Granite 4.1 3B, not the base. IBM's HuggingFace naming convention has `granite-4.1-3b` as the instruct model and `granite-4.1-3b-base` as the base. For v0.2 LoRA training, the base variant is the cleaner target.
```

**Update the "longer arc" section:**
- v0.1: imperfect classifier — DONE, shipped at 65% partial
- v0.2: LoRA-tuned classifier (~85% accuracy target)
- v0.3+: as previously described

### 2. `docs/brainstorm/reframes/cognitive_nature_as_perceptual_lens.md`

Find references to specific LoRA target models. Update Granite 4 Micro references to Granite 4.1 3B base.

Specific changes:

**Replace any references to "Granite 4 Micro (3B) for VRAM comfort" or similar Granite 4.0 mentions with:**

> "Granite 4.1 3B base (dense, Apache 2.0). Round 2 calibration validated the dense architecture as the strongest substrate (Granite 4.1 3B instruct at 58% partial / 73% Pass 1 quadrant — best of 13 tested models). The base variant is the v0.2 LoRA training target; the instruct variant is already in production as the v0.1.0 substrate."

**Update the "What this asks of us now" section:**
- Confirm the empirical justification: Round 2 calibration data + 50-chunk validation run
- The "model whose representations are organized around the 16 categories" trajectory still describes v0.5+, but v0.2's first LoRA pass is now scoped to a specific model

### 3. `docs/brainstorm/architecture/counsel_swarm_cognition.md`

Add a new section near the bottom (before "Open questions") capturing the empirical disagreement-as-signal data from the 13-model calibration.

**New section content:**

```markdown
## Diverse failure modes — empirical support from calibration data

The multi-model calibration runs (Round 1 + Round 2) produced data that directly supports the counsel approach. Specifically: **different models miss different fixtures**, with limited overlap in failure modes.

For example, Qwen 3.5 9B and Granite 4.1 3B both scored 58% partial accuracy at baseline, but their miss lists were substantially different:

- Both models miss: clear_07, clear_11, hard_01, hard_02, hard_03, hard_04, hard_05, hard_07, hard_11
- Qwen 9B uniquely misses fixtures Granite 3B gets right
- Granite 3B uniquely misses fixtures Qwen 9B gets right

A counsel including both models would correctly classify fixtures that either alone misses — by virtue of the other model getting it right. The Round 1 + Round 2 data (13 models × 30 fixtures × 3 runs each = 1170 individual classifications with perfect determinism) provides the substrate for selecting counsel members in v0.2+ based on failure-mode diversity, not just on individual accuracy.

The original observation from Round 1 also held in Round 2: **5 fixtures had 0 of 13 models classify correctly.** The fixture audit (`docs/agent/fixture_audit_round2.md`) determined that these were label issues, not model failures — when 13 architecturally diverse models converge on a different answer than the label, the label is more suspect than the models. This is the inverse of the usual ML failure analysis (where consensus failure is treated as a hard problem); for counsel cognition, consensus failure is diagnostic about the test data, not the test takers.

When v0.2 counsel mode comes online, the candidate selection should weight by failure-mode diversity. Two 60%-accurate models with disjoint failure modes are more useful than two 70%-accurate models with overlapping failure modes. The 1170-classification dataset is the empirical foundation for this selection.
```

This adds empirical grounding to the architecture doc — it now points at real data, not just theoretical reasoning.

### 4. Update `docs/brainstorm/README.md` lightly

Update the "Current contents" section to note Phase 2 has shipped:

In the "## Current contents" section, add a brief status note:

```markdown
**Status:** v0.1.0 shipped on 2026-06-06. Several reframes here have transitioned from hypothesis to implemented architecture. Where docs reflect that transition, they note "What actually shipped" sections. Docs that remain hypothetical (counsel mode, cognitive nature as perceptual lens) describe future-state architecture.
```

This signals to future readers when the docs were written relative to when ideas became reality.

## Don't list

- Do NOT rewrite the docs from scratch
- Do NOT remove existing content (just update specific outdated references)
- Do NOT introduce new architectural claims beyond what the data supports
- Do NOT touch other brainstorm docs not mentioned here
- Do NOT update DEFERRED_DOCS.md unless something is no longer deferred (which would be a strange reason to update it)

Preserve voice and structure. These are surgical updates plus one substantive addition.

## Output

Edit the files in place. After editing, briefly report what changed in each doc (1-2 sentences each).

## Time estimate

~30-40 minutes for the four touchpoints (three doc edits + README status update).
