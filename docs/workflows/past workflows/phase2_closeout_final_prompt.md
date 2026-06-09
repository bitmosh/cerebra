# Phase 2 Close-Out — Final Pass (v0.1.0)

Final structured pass to close Phase 2 at v0.1.0. Supersedes the earlier `phase2_closeout_prompt.md` — that prompt was written before the multi-model calibration and second fixture audit completed. This version incorporates:

1. **Production model swap** — Qwen 3.5 9B → Granite 4.1 3B base (per Round 2 calibration data and the validation run)
2. **Second fixture audit** — apply the 4 verdicts from `docs/agent/fixture_audit_round2.md`
3. **Existing close-out scope** — two-pass classifier, temperature 0.0, Migration005, 0.5-credit scoring

Read the whole prompt first. Execute phase by phase. STOP gates between phases — match expected state, continue; mismatch, report and pause.

## Context for the substrate change

The Round 2 multi-model calibration validated Granite 4.1 3B base as the right production substrate:

- Same accuracy as Qwen 3.5 9B (58% partial)
- Higher Pass 1 quadrant accuracy (73% vs 67% — best of any tested model)
- Smaller VRAM (3.7GB vs 8.9GB)
- Faster inference (2.4s vs 3.3s)
- No thinking-mode contamination (Granite 4.1 is explicitly non-reasoning)
- Apache 2.0 license
- Same model becomes v0.2 LoRA target — no production swap needed at version bump

The 50-chunk validation run cleared Granite 4.1 3B for backfill: 0 parse failures, 0 refusals, calibrated confidence behavior, ~32 minutes estimated for 740-chunk backfill.

## Reference docs to read first

Before starting, read:

- `docs/agent/multi_model_comparison.md` and `multi_model_comparison_round2.md` — calibration data justifying the substrate switch
- `docs/agent/granite41_3b_validation.md` — end-to-end validation
- `docs/agent/fixture_audit_round2.md` — the 4 fixture changes to apply
- `tests/fixtures/sku_fixtures.py` — current fixture state
- `tests/integration/test_sku_fixtures.py` — current calibration test
- `cerebra/cognition/sku_classifier.py` — current single-pass classifier and v1.1.0 prompt
- `cerebra/cognition/llm_adapter.py` — current LLM adapter
- `docs/agent/deviations/v0.1.0.md` — running deviation log

## Don't list

- Do NOT change the SKU taxonomy (16 D1 categories stay)
- Do NOT touch D2/D3 stubbing logic
- Do NOT modify Phase 0/1 ingest beyond Migration005
- Do NOT change the merge gate Discord protocol — same flow as v0.0.1a
- Do NOT iterate on the v2.0.0 two-pass prompts during this pass
- Do NOT add new fixtures
- Do NOT exceed the 4 fixture changes from the Round 2 audit

---

## Phase 1 — Fixture file changes from Round 2 audit

**Goal:** Apply the 4 verdicts from `docs/agent/fixture_audit_round2.md` to `tests/fixtures/sku_fixtures.py`.

### Tasks

1. **clear_07** — MARK_AMBIGUOUS:
   - Change `difficulty="clear"` to `difficulty="ambiguous"`
   - Add `ambiguous_with=D1Category.OBSERVATION`
   - Update notes field to reflect the OBSERVATION/DESIGN ambiguity

2. **clear_11** — MARK_AMBIGUOUS:
   - Change `difficulty="clear"` to `difficulty="ambiguous"`
   - Add `ambiguous_with=D1Category.OBSERVATION`
   - Update notes field

3. **hard_02** — RELABEL primary + change ambiguous_with:
   - Change `expected_d1=D1Category.MECHANISM` to `expected_d1=D1Category.DESIGN`
   - Change `ambiguous_with=D1Category.DESIGN` to `ambiguous_with=D1Category.PRINCIPLE`
   - Update notes field — this is now "DESIGN primary (architectural inversion choice), PRINCIPLE alternative (normative framing of permission rules)"
   - Note: this is the inverse of the first audit's marking. The Round 2 calibration data showed 0/13 models picked the old MECHANISM primary. The flip is data-driven.

4. **hard_07** — FIX ambiguous_with only (primary unchanged):
   - Keep `expected_d1=D1Category.DESIGN`
   - Change `ambiguous_with=D1Category.PRINCIPLE` to `ambiguous_with=D1Category.TECHNIQUE`
   - Update notes field — DESIGN primary stays correct; TECHNIQUE is the actual defensible alternative (procedural second sentence framing)

### Assertions update

After the changes:
- `CLEAR_FIXTURES` count drops from 13 to 11 (clear_07 and clear_11 move to ambiguous)
- `AMBIGUOUS_FIXTURES` count grows from 2 to 4
- `HARD_FIXTURES` stays at 15

Update the assertions at the bottom of `sku_fixtures.py`:

```python
assert len(SKU_FIXTURES) == 30, f"Expected 30 fixtures, got {len(SKU_FIXTURES)}"
assert len(CLEAR_FIXTURES) == 11, f"Expected 11 clear fixtures, got {len(CLEAR_FIXTURES)}"
assert len(AMBIGUOUS_FIXTURES) == 4, f"Expected 4 ambiguous fixtures, got {len(AMBIGUOUS_FIXTURES)}"
assert len(HARD_FIXTURES) == 15, f"Expected 15 hard fixtures, got {len(HARD_FIXTURES)}"
```

### Verification

```bash
python -c "from tests.fixtures.sku_fixtures import SKU_FIXTURES, CLEAR_FIXTURES, AMBIGUOUS_FIXTURES, HARD_FIXTURES; print(len(SKU_FIXTURES), len(CLEAR_FIXTURES), len(AMBIGUOUS_FIXTURES), len(HARD_FIXTURES))"
```

Expected output: `30 11 4 15`

**STOP gate:** Report fixture changes complete. Quote the diff of the 4 fixtures so I can verify the audit was applied correctly. Do not proceed until I confirm.

---

## Phase 2 — Production model swap

**Goal:** Switch the LLMAdapter's production model from Qwen 3.5 9B to Granite 4.1 3B base.

### Tasks

1. **Update `cerebra/cognition/llm_adapter.py`** (or wherever the production model is configured):
   - Change the default model identifier from the Qwen 3.5 9B Ollama tag to `huggingface.co/unsloth/granite-4.1-3b-GGUF:Q4_K_M`
   - If the model identifier is read from environment variable or config, update the default
   - Keep the ability to override (constructor parameter or env var) — don't hardcode the new model in a way that removes flexibility

2. **Update any default-model documentation:**
   - `docs/refined-runtime-model/CEREBRA_INGESTION_ARCHITECTURE.md` if it names the model
   - `README.md` or any setup doc that mentions the model
   - Comments in the classifier code

3. **Document the swap in the deviation log** (`docs/agent/deviations/v0.1.0.md`):
   - Why the swap (Round 2 calibration data, validation run)
   - What it improves (Pass 1 quadrant accuracy, latency, VRAM)
   - What unchanged (overall partial accuracy on calibration)
   - The substrate-for-LoRA reframe (production model = v0.2 LoRA target)
   - Note that Qwen 3.5 9B remains a viable fallback if Granite proves problematic in production

4. **Smoke test** — instantiate the classifier with the new default and run it on 3 fixtures by hand. Verify outputs are well-formed JSON with both pass results. This catches any plumbing issues before the full calibration test.

### Verification

- New default model is `huggingface.co/unsloth/granite-4.1-3b-GGUF:Q4_K_M`
- Smoke test passes on 3 fixtures
- Deviation log entry written

**STOP gate:** Report model swap complete with smoke test output. Wait for confirmation before proceeding.

---

## Phase 3 — Scoring change in calibration test

**Goal:** Update `tests/integration/test_sku_fixtures.py` to award 0.5 credit when the model's prediction matches `ambiguous_with`.

### Tasks

1. Find the scoring function in `test_sku_fixtures.py`. Update it to track both strict and partial-credit scores:

   ```python
   strict_correct = 0
   partial_correct = 0.0
   
   for fixture in SKU_FIXTURES:
       result = classifier.classify(fixture.content)
       predicted = result.primary
       
       if predicted == fixture.expected_d1:
           strict_correct += 1
           partial_correct += 1.0
       elif fixture.ambiguous_with is not None and predicted == fixture.ambiguous_with:
           partial_correct += 0.5
       # else: no credit either way
   
   strict_accuracy = strict_correct / len(SKU_FIXTURES)
   partial_accuracy = partial_correct / len(SKU_FIXTURES)
   ```

2. The merge gate report must show BOTH numbers:
   ```
   Strict accuracy: X/30 = Y%
   Partial-credit accuracy: X.5/30 = Y% (with 0.5 credit on N ambiguous fixtures matching ambiguous_with)
   ```

3. **Gate threshold change:** The merge gate uses **partial-credit accuracy** but the threshold for v0.1.0 is **NOT the original 70%**. The substrate-for-LoRA reframe changes the gate criterion to:
   - Partial-credit accuracy ≥ 60% (proves the architecture works above noise)
   - Reproducibility verified (perfect determinism at temp 0.0)
   - Errors clustered around known confusable pairs (proves trainable failure modes)
   - 4-quadrant calibration shows confidence correlates with correctness

   If all four pass, Phase 2 ships at v0.1.0 with the substrate-for-LoRA framing documented.

4. **Add unit tests** for the new scoring logic:
   - Model predicts `expected_d1` → +1.0 to both strict and partial
   - Model predicts `ambiguous_with` on a fixture with that field set → +0.5 to partial only
   - Model predicts something else → +0 to both
   - Edge case: fixture with `ambiguous_with=None` and model predicts wrong → 0 to both (no false partial credit)

### Verification

- Scoring function tracks both counters
- Both accuracy numbers reported
- Gate uses partial-credit accuracy with the new substrate-for-LoRA criteria
- Unit tests pass

**STOP gate:** Report scoring changes complete with sample report output showing both numbers. Wait for confirmation.

---

## Phase 4 — Migration005 for pass_count

**Goal:** Add `pass_count` column to `sku_assignments` table.

Note: if this was already shipped in an earlier session, skip this phase and verify the column exists. If not present, implement.

### Tasks

1. Verify if Migration005 already exists:
   ```bash
   ls cerebra/storage/migrations/ | grep -i pass_count
   ```

2. If not present, create `cerebra/storage/migrations/migration005_add_pass_count.py`:
   ```python
   # Up migration: add pass_count column with default 1
   ALTER TABLE sku_assignments ADD COLUMN pass_count INTEGER NOT NULL DEFAULT 1;
   UPDATE schema_version SET version = 5 WHERE id = 1;
   ```

3. Make it idempotent (check column existence before adding).

4. Update `SKUAssignment` dataclass in `cerebra/cognition/sku.py` to include `pass_count: int = 1`.

5. Update `cerebra/storage/sqlite_store.py` `insert_sku_assignment` to write `pass_count` (default 2 for v2.0.0 prompts since they're always two-pass).

6. Update query methods to populate `pass_count` from the row.

### Verification

- Migration runs cleanly on fresh vault
- Migration is idempotent on existing vault
- Storage round-trip preserves `pass_count`
- Existing storage tests pass

**STOP gate:** Report Migration005 status (already-present or implemented). Wait for confirmation.

---

## Phase 5 — Two-pass classifier verification

**Goal:** Verify the two-pass classifier is correctly implemented. If it was implemented in a previous session, verify; if not, implement.

### Tasks

1. Verify `cerebra/cognition/sku_classifier.py` has:
   - `PROMPT_VERSION = "2.0.0"`
   - Two-pass classification flow (Pass 1 quadrant, Pass 2 within-quadrant)
   - Pass 2 always fires (does not skip based on Pass 1 confidence)
   - `raw_scores_json` stores both pass results
   - `pass_count=2` on the resulting assignment
   - Inspector events emit at each pass

2. If two-pass is not yet implemented, refer to `docs/agent/phase2_response2.md` for the prompt specs and implementation guidance.

3. Test the classifier output shape on one fixture by hand — verify the JSON has the expected structure with both pass results.

### Verification

- PROMPT_VERSION is "2.0.0"
- Single `classify()` call produces a result with `pass_count=2` and both pass scores in `raw_scores_json`
- Sample output JSON is well-formed

**STOP gate:** Report two-pass implementation status with sample output. Wait for confirmation.

---

## Phase 6 — Temperature 0.0 verification

**Goal:** Confirm production uses temperature 0.0.

### Tasks

1. In `cerebra/cognition/llm_adapter.py`, verify `temperature=0.0` is the production default.

2. If `temperature` is a constructor parameter, verify the default is 0.0.

3. Verify the calibration test can override to 0.1 if needed for variance analysis (not used for the merge gate run).

### Verification

- Default classifier uses temperature 0.0
- Same fixture twice produces identical output (perfect determinism)

**STOP gate:** Report temperature setting verified. Wait for confirmation.

---

## Phase 7 — Run calibration with everything in place

**Goal:** Execute the calibration test with all changes applied (Granite 4.1 3B + fixture audit + two-pass + temperature 0.0 + 0.5-credit scoring).

### Tasks

1. Run the calibration test:
   ```bash
   pytest tests/integration/test_sku_fixtures.py::test_sku_calibration_70pct_top1 -v -s
   ```
   
   (Note: the test name still says "70pct" from before the reframe. Don't rename it — just update the threshold logic. The test name preservation keeps git history clean.)

2. Capture output. Expected to include:
   - Strict accuracy: X/30 = Y%
   - Partial-credit accuracy: X.5/30 = Y%
   - 4-quadrant table
   - Clear-case (11 fixtures): X/11
   - Ambiguous-case (4 fixtures): X/4 with credit breakdown
   - Hard-case (15 fixtures): X/15
   - Pass 1 quadrant accuracy
   - Pass 2 within-quadrant accuracy
   - Per-call latency
   - List of wrong fixtures

3. Expected result: ~60-65% partial-credit accuracy (per audit predictions). If this is met AND the other gate criteria are met, proceed to merge gate.

4. If significantly worse than expected (<50% partial), STOP. Report and wait for guidance.

### Verification

- Test completes
- All metrics reported
- Deviation log updated with results

**STOP gate:** Always stop here regardless of pass/fail. Report results in full. Wait for confirmation before proceeding to merge gate.

---

## Phase 8 — Full backfill validation (small scale)

**Goal:** Before the full 740-chunk backfill, run on 50 chunks to confirm production behavior matches the calibration test.

This is a sanity check, not a separate validation pass. We already did the standalone validation in `docs/agent/granite41_3b_validation.md`; this is just verifying the production code path produces the same behavior as the standalone validation script.

### Tasks

1. Run `cerebra classify` on 50 chunks selected from the vault.
2. Capture:
   - Parse failures
   - Latency distribution
   - Confidence distribution
3. Compare to the validation report's numbers. If broadly consistent, proceed.

### Verification

- 0 parse failures expected
- Mean latency ~2.5s
- No anomalies

**STOP gate:** Report 50-chunk run. Wait for confirmation before full backfill.

---

## Phase 9 — Full backfill

**Goal:** Run `cerebra classify` on all 740 unclassified records.

### Tasks

1. Run the backfill:
   ```bash
   cerebra classify --vault ~/cerebra-vaults/dev/
   ```

2. Monitor progress. Expected ~32 minutes per validation report.

3. Capture:
   - Total time
   - Mean latency per chunk
   - Parse failure count
   - Final coverage (all 740 records have SKUs assigned)
   - Distribution of D1 categories across the backfill
   - Distribution of confidence scores

4. Spot-check 10 random assignments by reading the chunk content and the assigned SKU. Are they reasonable? This is fast — just confirms nothing systematic is broken.

### Verification

- All 740 records have SKUs
- 0 parse failures (or near-zero)
- D1 distribution isn't catastrophically skewed (e.g., 600 of 740 classified as OBSERVATION = problem)
- Spot-checked assignments seem reasonable

**STOP gate:** Report backfill results. Wait for confirmation before proceeding to merge gate.

---

## Phase 10 — Merge gate

Only proceed if Phase 7 calibration met the substrate-for-LoRA gate criteria AND Phase 9 backfill completed cleanly.

### Tasks

1. Update `docs/agent/deviations/v0.1.0.md` with the full Phase 2 close-out narrative:
   - Two-pass architecture change
   - Production model swap (Qwen 9B → Granite 4.1 3B)
   - Round 2 fixture audit applied (4 fixtures changed)
   - Migration005 added
   - 0.5-credit scoring implemented
   - Temperature 0.0 deterministic backfill
   - Final calibration result with both numbers
   - Backfill statistics

2. Draft the PASS COMPLETE message for #changelog. Format (≤1800 chars, verify with `len()`):

```
── PASS COMPLETE · v0.1.0 · 2026-06-06 ──
Title: SKU Classifier — Phase 2 Close-Out with Granite 4.1 3B Substrate
Summary: Phase 2 closes at v0.1.0. Two-pass classifier (quadrant + within-quadrant), Granite 4.1 3B production substrate, temperature 0.0 deterministic backfill, Migration005 pass_count, Round 2 fixture audit (4 fixtures). Partial-credit accuracy: X%. Full 740-chunk backfill complete.
Project: cerebra
Highlights:
  · Granite 4.1 3B base replaces Qwen 3.5 9B (Pass 1 quadrant 73% vs 67%, 3.7GB vs 8.9GB VRAM)
  · Two-pass classifier (PROMPT_VERSION 2.0.0)
  · Migration005 adds pass_count column
  · 0.5-credit scoring for ambiguous fixtures
  · Round 2 fixture audit: clear_07/clear_11 → ambiguous; hard_02 relabeled; hard_07 ambiguous_with corrected
  · Backfill: 740 records, ~X minutes, 0 parse failures
Learnings:
  · Substrate-for-LoRA reframe: v0.1 accuracy = training corpus quality, not destination
  · Perfect determinism confirmed across 13-model calibration
  · Per-pair disambiguation will be v0.2+ work
Commit: <sha7>
Tests: X passed · 0 failed · 0 skipped
Branch: clean
```

3. Post the MERGE GATE to #approve-this with the PASS COMPLETE draft.

4. Wait for user approval.

5. After approval: commit, post PASS COMPLETE verbatim to #changelog, `bumper bump --dry`, BUMP+PUSH GATE.

**STOP gate:** Standard merge gate protocol — do not commit, push, or bump without explicit Discord approval.

---

## Total scope estimate

- Phase 1 (fixture audit changes): 30 minutes
- Phase 2 (model swap): 20 minutes
- Phase 3 (scoring change): 30 minutes
- Phase 4 (Migration005 — possibly already done): 0-30 minutes
- Phase 5 (two-pass verification — possibly already done): 0-60 minutes
- Phase 6 (temperature 0.0): 5 minutes
- Phase 7 (calibration run): 5 minutes runtime + analysis
- Phase 8 (50-chunk sanity): 5 minutes
- Phase 9 (full backfill): ~32 minutes runtime
- Phase 10 (merge gate + Discord flow): 30 minutes

Total: ~3-4 hours of focused work with STOP gates between phases.

## If something feels off

Report and pause. The Don't list is load-bearing. Don't introduce changes outside the declared scope.

## What this prompt does NOT cover

- Brainstorm doc updates (separate prompt `brainstorm_docs_update_prompt.md`)
- v0.2 LoRA planning (after Phase 2 ships)
- v0.1.1 work (any follow-ups after Phase 2)
- Counsel-mode infrastructure (v0.3+)

Those are deliberately deferred. Phase 2 ships first; everything else follows.
