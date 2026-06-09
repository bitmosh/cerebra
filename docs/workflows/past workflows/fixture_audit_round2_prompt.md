# Second Fixture Audit — 4 Consensus-Failure Fixtures

After 13 models tested across Round 1 and Round 2, four fixtures still have NO model getting them correct (strict). The pattern strongly suggests label issues rather than uniform model failure.

The 4 fixtures: `clear_07`, `clear_11`, `hard_02`, `hard_07`

This is the same audit pattern as the first round (which moved 4 fixtures to ambiguous status and shifted baseline accuracy from 47% to 60%). The goal is to identify whether any of these 4 should be relabeled, marked ambiguous, or kept as-is.

## Reference materials

Read before deciding:

- `tests/fixtures/sku_fixtures.py` — current state of each fixture (including the 4 ambiguous markings from the first audit)
- `docs/agent/multi_model_comparison.md` — Round 1 model predictions per fixture
- `docs/agent/multi_model_comparison_round2.md` — Round 2 model predictions per fixture
- `docs/agent/multi_model_comparison_raw.json` — Round 1 raw data with all 11 models' predictions
- `docs/agent/multi_model_comparison_raw_round2.json` — Round 2 raw data with Granite 4.1 predictions
- `docs/refined-runtime-model/CEREBRA_SKU_ADDRESSING.md` — the 16-category taxonomy with definitions

## The 4 fixtures to audit

For each fixture below, perform the same verdict format as the first round: KEEP / RELABEL_TO_X / MARK_AMBIGUOUS with reasoning.

### clear_07 (label: DESIGN)

Content:
> "The approval gate is a workflow convention, not a CLI feature. bumper renders and traces, and you (or your agent) post a dry-run sample for approval before the live bump."

What 13 models said: split across OBSERVATION (many), PHENOMENON, MECHANISM, GOAL, TECHNIQUE — none picked DESIGN.

Questions to consider:
- Is "the approval gate is X, not Y" framing more design-decision language or more declarative-fact language?
- Does this describe an intentional architectural choice (DESIGN) or report how the system actually behaves (OBSERVATION/MECHANISM)?
- Could the second sentence (procedural "bumper renders and traces, and you post...") be tipping models toward TECHNIQUE?

### clear_11 (label: EVENT)

Content:
> "Phase 0 complete at commit 5747c7e on 2026-06-04. 88 tests passed. Repository initialized, governance loaded, first vault created successfully."

What 13 models said: Almost all said OBSERVATION. None picked EVENT.

Questions to consider:
- Is "Phase 0 complete" describing a happening-at-a-moment (EVENT) or a measured-current-state (OBSERVATION)?
- The numbers ("88 tests passed", "commit 5747c7e") read as measurements/data — does this dominate?
- Does the framing "X happened at time Y" require human reading to see EVENT, while surface reading produces OBSERVATION?

### hard_02 (label: MECHANISM, ambiguous_with: DESIGN per first audit)

Content:
> "The leeway network inverts prohibition models. Instead of specifying what is forbidden, it specifies what is permitted under what conditions. Everything outside the network is implicitly disallowed."

What 13 models said: Many said DESIGN (the ambiguous_with category) — these would get 0.5 credit. Others said PRINCIPLE or JUDGMENT.

Questions to consider:
- Is this fixture's PRIMARY label still correct (MECHANISM) given that the unanimous "wrong" answer is DESIGN?
- Should DESIGN become the primary label and MECHANISM the ambiguous alternative? That's the inverse of current.
- Does "inverts prohibition models" + "instead of X, it does Y" read more as design-decision or as causal-mechanism description?

### hard_07 (label: DESIGN)

Content:
> "Phase 2 scope: assign D1, D4, D9, D10 digits using the classifier; stub D2, D3 as 0x0 with subcategory_strategy_version='v1-stub'; defer D5, D6 to v0.2."

Wait — this is the wrong content for hard_07. Let me check. Looking again at the data, hard_07 in the fixture file is actually the approval gate one, same as clear_07. That's suspicious — same content with different labels? Verify what hard_07 actually is.

If hard_07 truly contains the same content as clear_07 but with a different label or framing, that's itself a fixture-set issue worth flagging.

What 13 models said: Most picked TECHNIQUE, MECHANISM, or GOAL. None picked DESIGN.

Questions to consider:
- Is the content really DESIGN (scoping decisions) or TECHNIQUE (procedural how-to)?
- The format "assign X, stub Y, defer Z" is imperative — does that read more procedural?

## Process

For each fixture:

1. Quote the content verbatim
2. List the model predictions distribution (use raw JSON data, group by predicted_d1)
3. State your verdict (KEEP / RELABEL_TO_X / MARK_AMBIGUOUS)
4. Provide reasoning grounded in the category definitions from `CEREBRA_SKU_ADDRESSING.md`
5. Note if any pattern emerges across the 4 fixtures (e.g., all involve declarative-fact-framing vs procedural framing)

## Output format

Write `docs/agent/fixture_audit_round2.md` with:

1. Section per fixture (verdict + reasoning)
2. Summary section: how many KEEP / RELABEL / MARK_AMBIGUOUS, what the implied accuracy ceiling becomes if all relabels are applied
3. Recommendation: if/which fixtures to update in `sku_fixtures.py`

DO NOT modify `sku_fixtures.py` directly in this pass. Output the audit findings; user decides which to apply before next calibration run.

## Don't list

- Do NOT modify the fixture file
- Do NOT re-run any calibration
- Do NOT change the taxonomy
- Do NOT add new fixtures
- Do NOT touch the scoring logic

This is pure analytical work producing a recommendation document.

## Time estimate

30-60 minutes of careful reading and analysis. Each fixture deserves real consideration — these are calibration-set decisions that affect future LoRA training data quality.
