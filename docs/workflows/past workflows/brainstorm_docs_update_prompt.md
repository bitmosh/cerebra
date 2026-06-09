# Brainstorm Docs Update — Round 2 Calibration Findings

Update three brainstorm docs in `docs/brainstorm/` with findings from the Round 2 multi-model calibration. Light edits to reflect current data, not rewrites.

## Context

The brainstorm directory was created in this session capturing the architectural thinking that emerged during Phase 2. Several of these docs reference specific models (OLMo 3, Granite 4 Micro) as candidates based on Round 1 data. Round 2 added Granite 4.1 calibration data that changes which models are the leading candidates.

The docs don't need major rewrites — just specific factual updates and the addition of one new finding (per-model failure-mode diversity).

## Reference for the updates

- `docs/agent/multi_model_comparison.md` — Round 1 results
- `docs/agent/multi_model_comparison_round2.md` — Round 2 results
- `docs/brainstorm/` — the existing docs to update

## Docs to update

### 1. `docs/brainstorm/reframes/v01_as_substrate_for_lora.md`

Find references to OLMo 3 as the recommended LoRA training target. Update to Granite 4.1 3B based on Round 2 data.

Specific edits:

**Current language to replace:**
> "This argues for OLMo 3 7B as the LoRA target (full transparency, model flow approach) even if it doesn't score best on initial calibration."

**Replace with something like:**
> "Round 2 calibration data shifted the LoRA target recommendation to Granite 4.1 3B. Round 2 results: Granite 4.1 3B base scored 58% partial accuracy — tying Qwen 3.5 9B instruct — with 73% Pass 1 quadrant accuracy (highest of any model tested). At 3B dense, it's the most LoRA-trainable substrate that performs at production-model quality. OLMo 3 remains a secondary candidate / fallback for the model-flow capabilities if Granite training doesn't yield expected results, but Granite 4.1 3B is the primary path."

Also update the "destination" section that mentions specific models. The reasoning chain stays — smaller, faster, documented training methodology — just the model identity changes.

### 2. `docs/brainstorm/reframes/cognitive_nature_as_perceptual_lens.md`

Find any references to specific LoRA target models. Update Granite 4 Micro references to Granite 4.1 3B.

Specific edits:

**Current language (search for):**
> "Granite 4.0 Micro (3B) for VRAM comfort"
> or similar references to Granite 4 Micro as the v0.2 candidate

**Replace with:**
> "Granite 4.1 3B (dense, 3B parameters, Apache 2.0). Round 2 calibration validated this as the strongest LoRA candidate — 58% partial accuracy at baseline (matching Qwen 3.5 9B instruct), 73% Pass 1 quadrant accuracy, and explicit IBM positioning for fine-tuning use cases. Same model serves as both v0.1.0 production substrate and v0.2 LoRA target, cleanly avoiding the swap-models-at-version-bump complexity."

### 3. `docs/brainstorm/architecture/counsel_swarm_cognition.md`

Add a new section near the bottom (before "Open questions") about the per-model failure-mode diversity finding from Round 1 + Round 2 data.

**New section content:**

```markdown
## Diverse failure modes — empirical support from calibration data

The multi-model calibration runs (Round 1 + Round 2) produced data that directly supports the counsel approach. Specifically: **different models miss different fixtures**, with limited overlap in failure modes.

For example, Qwen 3.5 9B and Granite 4.1 3B both score 58% partial accuracy on the calibration set, but their miss lists are substantially different:

- Qwen 9B uniquely misses: clear_07, clear_10, clear_12, clear_13, hard_05, hard_09, hard_12
- Granite 4.1 3B uniquely misses: clear_04, clear_08, clear_15, hard_14
- Both miss: clear_11, hard_01, hard_02, hard_03, hard_04, hard_07, hard_11

The blind spots don't overlap completely. A counsel including both models would correctly classify fixtures that either alone misses, simply by virtue of the other model getting it right.

This is the empirical validation of counsel cognition's central claim: **disagreement among diverse models is signal, not noise**. The 13-model calibration data is the foundation for selecting counsel members in v0.2+. Models with maximally different failure patterns make the best counsel partners.

When v0.2 counsel mode comes online, the candidate selection should weight by failure-mode diversity, not just by individual model accuracy. Two 60%-accurate models with disjoint failure modes are more useful than two 70%-accurate models with overlapping failure modes.
```

This adds empirical grounding to the architecture doc — it now points at real data, not just theoretical reasoning.

## Don't list

- Do NOT rewrite the docs from scratch
- Do NOT remove existing content (just update specific outdated references)
- Do NOT introduce new architectural claims beyond what the data supports
- Do NOT touch other brainstorm docs not mentioned here
- Do NOT update the README or DEFERRED_DOCS unless necessary for consistency

Preserve voice and structure. These are minor factual updates plus one substantive addition.

## Output

Edit the three files in place. No new files. After editing, briefly report what changed in each doc (1-2 sentences each).

## Time estimate

~20-30 minutes total. Small surgical edits.
