# Phase 2 Close-Out — Structured Pass

Bundled work to close Phase 2 at v0.1.0. This is a structured pass. Read the whole prompt first; note the phases, STOP gates, and the "Don't" list. Execute phase by phase. At each phase boundary, check actual state vs. expected; match → continue, mismatch → report and pause.

## Context

Phase 2 calibration on Qwen 3.5 9B with thinking-mode disabled returned 47% strict / 60% with partial credit on ambiguous fixtures. Terminal Claude consultation (`docs/agent/phase2_response2.md`) recommended: fixture audit, two-pass hierarchical classifier, temperature 0.0, Migration005 for `pass_count`, 0.5-credit scoring on ambiguous fixtures.

This prompt bundles all five into one pass. Target version: **v0.1.0**.

## Reference docs to read first

Before starting, read:

- `docs/agent/phase2_response2.md` — terminal Claude's full Round 2 consultation with two-pass prompts and rationale
- `tests/fixtures/sku_fixtures.py` — current fixture state (already edited partially)
- `tests/integration/test_sku_fixtures.py` — current calibration test
- `cerebra/cognition/sku_classifier.py` — current single-pass classifier and v1.1.0 prompt
- `cerebra/cognition/llm_adapter.py` — current LLM adapter (should already have thinking off)
- `docs/agent/deviations/v0.1.0.md` — running deviation log
- `cerebra/storage/migrations/` — existing migration files for the pattern

## Don't list

- Do NOT change the SKU taxonomy (16 D1 categories stay)
- Do NOT change the prompt-version schema field
- Do NOT switch the LLM model — keep on Qwen 3.5 9B for this pass; model comparison is a separate later pass
- Do NOT touch D2/D3 stubbing logic
- Do NOT modify Phase 0/1 ingest or storage layer beyond Migration005
- Do NOT change merge gate Discord protocol — same flow as v0.0.1a

## Phase 1 — Fixture file fixes

**Goal:** Get `tests/fixtures/sku_fixtures.py` into a state that imports cleanly and reflects the audit decisions.

**Tasks:**

1. The file currently has clear_02 and clear_13 marked `difficulty="ambiguous"` with `ambiguous_with=MECHANISM`. The assertions at the bottom will fail because `CLEAR_FIXTURES` count dropped from 15 to 13.

2. Add an `AMBIGUOUS_FIXTURES` derivation:
   ```python
   AMBIGUOUS_FIXTURES: list[SKUFixture] = [f for f in SKU_FIXTURES if f.difficulty == "ambiguous"]
   ```

3. Update assertions:
   ```python
   assert len(SKU_FIXTURES) == 30, f"Expected 30 fixtures, got {len(SKU_FIXTURES)}"
   assert len(CLEAR_FIXTURES) == 13, f"Expected 13 clear fixtures, got {len(CLEAR_FIXTURES)}"
   assert len(AMBIGUOUS_FIXTURES) == 2, f"Expected 2 ambiguous fixtures, got {len(AMBIGUOUS_FIXTURES)}"
   assert len(HARD_FIXTURES) == 15, f"Expected 15 hard fixtures, got {len(HARD_FIXTURES)}"
   ```

4. Update stale `notes` fields. Three fixtures have notes that reference the OLD `ambiguous_with` category:

   **clear_02** — current notes say "Classic TECHNIQUE." Update to acknowledge the ambiguity:
   ```
   "Procedural description of cerebra ingest. TECHNIQUE-as-described, but the passive-voice
   system-action language ('discovers, registers, parses') legitimately reads as MECHANISM
   too. Marked ambiguous — both answers defensible."
   ```

   **hard_01** — notes mention "vs TOOL (SKU as an instrument)". Update to mention RELATION:
   ```
   "PRINCIPLE (normative claim about SKU's load-bearing role: 'get this right and...') vs
   RELATION (structural dependency framing across components: SKU as substrate for truth
   tower, leeway network, dream/retrain). The causal framing tips toward PRINCIPLE but
   the dependency-mapping structure makes RELATION defensible."
   ```

   **hard_02** — notes mention "vs PRINCIPLE (normative rule)". Update to mention DESIGN:
   ```
   "MECHANISM (how the inversion works operationally: 'specifies what is permitted under
   what conditions') vs DESIGN (architectural choice: 'inverts prohibition models'). The
   first sentence is design-decision language; the rest is operational mechanism."
   ```

5. Verify the file imports cleanly:
   ```bash
   python -c "from tests.fixtures.sku_fixtures import SKU_FIXTURES, CLEAR_FIXTURES, AMBIGUOUS_FIXTURES, HARD_FIXTURES; print(len(SKU_FIXTURES), len(CLEAR_FIXTURES), len(AMBIGUOUS_FIXTURES), len(HARD_FIXTURES))"
   ```
   Expected output: `30 13 2 15`

**Verification:**
- File imports without AssertionError
- The 4 fixtures (clear_02, clear_13, hard_01, hard_02) have correct `ambiguous_with` values
- Stale notes updated
- Run `pytest tests/fixtures/` if there are any tests there

**STOP gate:** Report fixture changes complete. Do not proceed to Phase 2 until I confirm the fixtures look right.

---

## Phase 2 — Scoring change in calibration test

**Goal:** Update `tests/integration/test_sku_fixtures.py` to award 0.5 credit when the model's prediction matches `ambiguous_with`.

**Tasks:**

1. Find the scoring function in `test_sku_fixtures.py`. Look for where `predicted == expected` comparison happens. The function likely looks something like `_score_classification` or `_run_calibration` or is inline in `test_sku_calibration_70pct_top1`.

2. Update the scoring to track both strict and partial-credit scores:
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
           # No strict credit; 0.5 partial credit
           partial_correct += 0.5
       # else: no credit either way
   
   strict_accuracy = strict_correct / len(SKU_FIXTURES)
   partial_accuracy = partial_correct / len(SKU_FIXTURES)
   ```

3. The merge gate report must show BOTH numbers:
   ```
   Strict accuracy: X/30 = Y%
   Partial-credit accuracy: X.5/30 = Y% (with 0.5 credit on N ambiguous fixtures matching ambiguous_with)
   ```

4. The gate threshold check uses **partial-credit accuracy ≥ 0.70** (since that's the reframed success criterion). Strict accuracy is reported but not gating.

5. Add unit tests for the scoring logic itself. Three cases:
   - Model predicts `expected_d1` → +1.0 to both strict and partial
   - Model predicts `ambiguous_with` on a fixture where that's set → +0.5 to partial only
   - Model predicts something else → +0 to both
   
   Put these in `tests/unit/cognition/test_calibration_scoring.py` or similar — wherever the project convention puts unit tests for test logic.

**Verification:**
- New scoring function exists with both counters
- Threshold check uses partial accuracy
- Report output includes both numbers
- Unit tests for scoring pass

**STOP gate:** Report scoring changes complete with the test output showing both numbers reported correctly. Wait for my confirmation before proceeding to Phase 3.

---

## Phase 3 — Migration005 for pass_count

**Goal:** Add `pass_count` column to `sku_assignments` table. Defaults to 1 for v1.x assignments; v2.0+ assignments (two-pass) will set it to 2.

**Tasks:**

1. Create `cerebra/storage/migrations/migration005_add_pass_count.py` (or whatever naming convention exists — check `migration004`'s filename pattern and match exactly).

2. Migration content:
   ```python
   # Up migration: add pass_count column with default 1
   ALTER TABLE sku_assignments ADD COLUMN pass_count INTEGER NOT NULL DEFAULT 1;
   
   # Update schema_version
   UPDATE schema_version SET version = 5 WHERE id = 1;
   ```
   
   Use the exact migration pattern from Migration004 (`sku_assignments` table creation). Match the style.

3. The migration must be idempotent — running it twice should not fail. Check for column existence before adding.

4. Update the `SKUAssignment` dataclass in `cerebra/cognition/sku.py` to include `pass_count: int = 1`.

5. Update the storage layer (`cerebra/storage/sqlite_store.py`) `insert_sku_assignment` to write `pass_count`.

6. Update any storage query that returns `SKUAssignment` to populate `pass_count` from the row.

**Verification:**
- Migration runs cleanly on a fresh vault
- Migration runs cleanly on an existing v0.0.1a vault (idempotent test)
- `SKUAssignment` dataclass has the new field
- Storage round-trip preserves `pass_count`
- Run existing storage tests to confirm no regression

**STOP gate:** Report Migration005 complete. Wait for confirmation before proceeding.

---

## Phase 4 — Two-pass classifier implementation

**Goal:** Replace the single-pass v1.1.0 classifier with the two-pass hierarchical design from terminal Claude's `phase2_response2.md`. Bump `PROMPT_VERSION` to `"2.0.0"`.

**Tasks:**

1. Read `docs/agent/phase2_response2.md` Section "Decision 2 — Two-Pass Hierarchical Design" carefully. It contains the full Pass 1 (quadrant) prompt and four Pass 2 (within-quadrant) prompts. Use those prompts verbatim.

2. Implement Pass 1: quadrant selection. Returns one of: EMPIRICAL, GENERATIVE, NORMATIVE, RELATIONAL. The Pass 1 prompt is short (~1500 chars) and pattern-vocabulary-triggered, not reasoning-demanding.

3. Implement Pass 2: within-quadrant disambiguation. Four separate prompts, one per quadrant. Each only has to discriminate between the 4 categories in its quadrant. Per terminal Claude's recommendation: **Pass 2 ALWAYS fires** — do not skip based on Pass 1 confidence.

4. The classifier flow:
   ```python
   def classify(self, content: str) -> ClassificationResult:
       # Pass 1: quadrant
       pass1_result = self._classify_quadrant(content)
       
       # Pass 2: within-quadrant category (always fires)
       quadrant = pass1_result.quadrant
       prompt = self._get_pass2_prompt(quadrant)
       pass2_result = self._classify_within_quadrant(content, prompt)
       
       # Combine: pass2 d1 is the answer; pass1 quadrant scores stored for diagnosis
       return ClassificationResult(
           primary=pass2_result.primary,
           confidence=pass2_result.confidence,
           raw_scores_json={
               "pass1_quadrant_scores": pass1_result.scores,
               "pass2_category_scores": pass2_result.scores,
           },
           prompt_version="2.0.0",
           pass_count=2,
       )
   ```

5. The Pass 1 prompt should return JSON like `{"quadrant": "EMPIRICAL", "scores": {"EMPIRICAL": 0.7, "GENERATIVE": 0.1, "NORMATIVE": 0.1, "RELATIONAL": 0.1}, "confidence": 0.7}`.

6. Each Pass 2 prompt returns JSON like `{"primary": "MECHANISM", "scores": {"OBSERVATION": 0.1, "PATTERN": 0.05, "MECHANISM": 0.7, "PHENOMENON": 0.15}, "confidence": 0.7}`.

7. **Schema impact:** `raw_scores_json` already exists and is flexible (JSON column). Store both pass results inside it as shown above. No additional migration needed for storage — only the `pass_count` from Migration005.

8. Bump `PROMPT_VERSION` to `"2.0.0"` in `sku_classifier.py`.

9. Inspector events: every pass emits an event. So a single `classify()` call now produces TWO `SKUAssigned` events with different `pass_number` field, or one `SKUAssigned` event with both pass results embedded. Pick whichever fits existing patterns better; document the choice in the deviation log.

**Verification:**
- Both prompts compile (no syntax errors in JSON examples in prompts)
- A single `classify()` call produces a result with `pass_count=2` and both pass scores in `raw_scores_json`
- Run a smoke test on one fixture and verify the output shape
- Existing classifier unit tests updated for the new shape

**STOP gate:** Report two-pass implementation complete with a sample output JSON for one fixture. Wait for confirmation before proceeding to Phase 5.

---

## Phase 5 — Temperature 0.0 + determinism

**Goal:** Set the production backfill to use temperature 0.0 for reproducibility.

**Tasks:**

1. In `cerebra/cognition/llm_adapter.py` (specifically the `OllamaDirectAdapter._call_ollama_chat()` method or equivalent), expose `temperature` as a constructor parameter with default 0.0.

2. Update the classifier to use the production-default adapter with temperature 0.0.

3. The calibration test should be runnable with temperature override (for variance analysis later). Add a parameter to the test or fixture that allows temperature 0.1 explicitly when needed.

4. Document in the deviation log:
   - Why temperature 0.0 (reproducibility for stable SKUs)
   - The trade-off (less diversity in outputs, but production needs same chunk → same SKU)
   - Future: variance analysis at 0.1 may be useful for confidence calibration in v0.2

**Verification:**
- Default classifier instantiation uses temperature 0.0
- Running the same fixture twice produces the same output (modulo any remaining model nondeterminism)

**STOP gate:** Report temperature change complete. Wait for confirmation before proceeding to Phase 6.

---

## Phase 6 — Run calibration and produce results

**Goal:** Execute the calibration test with the new two-pass classifier and produce the merge gate report.

**Tasks:**

1. Run the calibration test:
   ```bash
   pytest tests/integration/test_sku_fixtures.py::test_sku_calibration_70pct_top1 -v -s
   ```

2. Capture the output. It should include:
   - Strict accuracy: X/30 = Y%
   - Partial-credit accuracy: X.5/30 = Y% (with 0.5 credit on N ambiguous fixtures)
   - 4-quadrant table (high/low confidence × correct/wrong)
   - Hard-case accuracy (15 fixtures): X/15
   - Clear-case accuracy (13 fixtures): X/13
   - Ambiguous-case accuracy (2 fixtures): X/2 with credit logic shown
   - Per-call latency: min, max, mean
   - Pass 1 quadrant accuracy: X/30
   - Pass 2 within-quadrant accuracy: X/30 (conditioned on Pass 1 correctness)
   - List of fixtures the model got wrong (fixture_id, expected, predicted, ambiguous_with status)

3. If partial-credit accuracy ≥ 0.70, proceed to merge gate.

4. If partial-credit accuracy < 0.70, STOP. Report the result and wait for guidance. Do not iterate on the prompt without direction.

**Verification:**
- Test completes
- All metrics above are reported
- The deviation log entry for v0.1.0 is updated with these results

**STOP gate:** Always stop here regardless of pass/fail. Report results in full. Wait for confirmation before proceeding to the merge gate.

---

## Phase 7 — Merge gate

Only proceed if Phase 6 results meet ≥70% partial-credit accuracy.

**Tasks:**

1. Update `docs/agent/deviations/v0.1.0.md` with:
   - The two-pass architecture change
   - The temperature 0.0 decision
   - The fixture audit (4 ambiguous markings)
   - The Migration005 addition
   - The 0.5-credit scoring change
   - Final calibration results

2. Draft the PASS COMPLETE message for #changelog. Format (≤1800 chars, verify with `len()`):

```
── PASS COMPLETE · v0.1.0 · 2026-06-05 ──
Title: SKU Classifier — Two-Pass Hierarchical with Ambiguity-Aware Scoring
Summary: Phase 2 closes at v0.1.0. Two-pass classifier (quadrant + within-quadrant) replaces single-pass v1.1.0. Temperature 0.0 for reproducibility. Migration005 adds pass_count. Fixture audit marks 4 cases as ambiguous with 0.5-credit scoring. Partial-credit accuracy: X% (≥70% gate cleared).
Project: cerebra
Highlights:
  · Two-pass classifier: Pass 1 quadrant (4-way), Pass 2 within-quadrant (4-way)
  · Pass 2 always fires (per terminal Claude consultation)
  · Migration005 adds pass_count column
  · Temperature 0.0 for deterministic SKU assignment
  · 0.5-credit scoring for ambiguous fixtures (clear_02, clear_13, hard_01, hard_02)
  · Stale fixture notes updated
Learnings:
  · The 47%→60% baseline shift came from fixture audit, not prompt change
  · The format-tax pattern partially addresses via two-pass separation
  · v0.1.0 substrate is good enough for v0.2 LoRA training corpus
Commit: <sha7>
Tests: X passed · 0 failed · 0 skipped
Branch: clean
```

3. Post the MERGE GATE to #approve-this with the PASS COMPLETE draft.

4. Wait for user approval before committing.

5. After approval: commit, post PASS COMPLETE verbatim to #changelog, run `bumper bump --dry`, post BUMP+PUSH GATE.

**STOP gate:** Standard merge gate protocol — do not commit, push, or bump without explicit Discord approval.

---

## Total scope estimate

- Phase 1: 20 minutes
- Phase 2: 30 minutes (including unit tests)
- Phase 3: 30 minutes (migration + storage layer changes)
- Phase 4: 60-90 minutes (two prompts + classifier rewrite)
- Phase 5: 15 minutes
- Phase 6: 10-15 minutes (calibration test runtime)
- Phase 7: 20 minutes (deviation log + PASS COMPLETE drafting)

Total: ~3-4 hours of focused work with STOP gates between phases.

## If something feels off

Report and pause. Don't try to fix things outside the declared scope. Don't introduce changes that weren't in this prompt.

The Don't list is load-bearing.
