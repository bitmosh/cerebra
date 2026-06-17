# Phase 9 Primitive Audit — Pre-Step 2 Codebase Inventory

**Date:** 2026-06-13
**Purpose:** Ground-truth inventory before Phase 9 Step 2 (CatalystEngine) kickoff
**Scope:** Read-only. No code was written or modified.

---

## Section 1 — Quick Answers

### Q1 — Does `cerebra/_primitives/` exist?

**ANSWERED — YES.**

`cerebra/_primitives/` exists and is fully populated:

```
cerebra/_primitives/
  __init__.py
  clutch.py
  mode_router.py
  score_composer.py
  tombstone_set.py
  trajectory.py
  triangulator.py
  VENDORED_FROM.md
```

`VENDORED_FROM.md` states: "Source: `docs/refined-runtime-model/LATTICA_PRIMITIVES.md` (doc set v8.1). Copied: 2026-06-04. Modifications: none — verbatim implementations per spec. The canonical reference for future updates lives in `cerebra/_primitives_canonical/`."

A `cerebra/_primitives_canonical/` directory also exists but contains only an empty `__init__.py`. The effective canonical reference is `docs/refined-runtime-model/LATTICA_PRIMITIVES.md`.

---

### Q2 — Where does the Clutch primitive actually live?

**ANSWERED — TWO locations with different shapes.**

- **`cerebra/_primitives/clutch.py`** — the Lattica primitive. Classes: `Clutch`, `Decision`, `Rule`. API: `Clutch.decide(signals: dict, state: dict) → Decision`. The primitive is generic (signals + state → Decision), dependency-free, and re-exported through `cerebra.cognition` for module-level consumers.

- **`cerebra/cognition/clutch.py`** — the Cerebra cycle-runtime consumer layer (Phase 8/9). Classes: `ClutchEngine`, `ClutchDecision`, `ClutchContext`, `ClutchCycleState`. This is NOT the primitive; it is the Cerebra-specific application of the Clutch pattern, built independently with typed cycle-context inputs.

The two do not share an inheritance relationship. `cerebra/cognition/__init__.py` imports `Clutch, Decision, Rule` from `cerebra._primitives` (the primitive) and separately the `cognition/clutch.py` contains `ClutchEngine` (the consumer). They coexist without conflict.

No imports of `from cerebra._primitives` were found in `cerebra/cognition/clutch.py` — the consumer does not inherit from or delegate to the primitive.

---

### Q3 — Do the other named primitives exist? Where?

**ANSWERED — All 5 found, all in `cerebra/_primitives/`.**

See Section 2 for the full table. All implementations are verbatim per LATTICA_PRIMITIVES.md spec; all are dependency-free (stdlib only).

---

### Q4 — Does ANY bandit primitive exist in Cerebra?

**ANSWERED — NO bandit primitive in Cerebra.**

Searches for `class.*Bandit`, `class.*MAB`, `class.*MultiArmed`, `arm_stats`, `epsilon_greedy`, `thompson_sampling`, `weighted_random_sample`, `exploration.*exploitation` returned no results across `cerebra/` or `tests/`.

No bandit test files found. No `test_*selector*` files found.

A bandit implementation exists at `/home/boop/Projects/ai-lab/core/bandit.py` (see Q7). It is not accessible from Cerebra at runtime — it's a separate project.

---

### Q5 — What's the precedent for new primitive placement?

**ANSWERED.**

All six Lattica primitives live in `cerebra/_primitives/`. Cerebra-specific consumers of the primitive patterns live in `cerebra/cognition/`. `cerebra/cognition/__init__.py` re-exports the primitives to provide a single import surface for module-level consumers. No primitive logic lives in `cerebra/cognition/` directly — `cognition/clutch.py` is the consumer (ClutchEngine), not the primitive (Clutch).

There is no `cerebra/core/` or `cerebra/lib/` namespace. The top-level structure is:

```
cerebra/
  _primitives/        ← vendored Lattica primitives (6 files)
  _primitives_canonical/  ← empty stub (future use)
  cli/
  cognition/          ← cycle runtime, consumers, SKU, signals
  governance/
  graph/
  ingest/
  inspector/
  memory/
  retrieval/
  sources/
  storage/
  vault/
```

---

### Q6 — Are there references to `lattica-primitives`?

**ANSWERED — Doc-only references. No runtime imports.**

References exist in five doc files:
- `docs/aseptic/tech_debt_seed.md` — describes it as a planned future extraction (TECH_DEBT entry)
- `docs/refined-runtime-model/LATTICA_PRIMITIVES.md` — defines the extraction plan
- `docs/refined-runtime-model/CEREBRA_DRIFT_FIXES_v8.1.md` — lists it in a package hierarchy diagram
- `docs/refined-runtime-model/CEREBRA_CATALYST.md` — "see lattica-primitives §Bandit Selector"
- `docs/refined-runtime-model/CEREBRA_OPEN_QUESTIONS.md`, `CEREBRA_SKU_ADDRESSING.md`

Zero Python imports of `from lattica.primitives` or `from lattica_primitives` anywhere in `cerebra/`. The extraction is planned-but-not-started.

Critical: `CEREBRA_CATALYST.md` references "lattica-primitives §Bandit Selector" as if a bandit primitive specification exists. No such section was found in `docs/refined-runtime-model/LATTICA_PRIMITIVES.md` (which only specifies the six current primitives). The Bandit Selector is referenced but not yet specified or implemented.

---

### Q7 — How does bons.ai's catalyst.py compare?

**ANSWERED — ACCESSIBLE at `/home/boop/Projects/ai-lab/core/catalyst.py` (304 lines).**

A companion `bandit.py` (106 lines) exists in the same directory.

**`ai-lab/core/bandit.py` — the bandit implementation:**
- Algorithm: UCB (Upper Confidence Bound), not Thompson Sampling or epsilon-greedy
- State shape: `dict[str, {"count": int, "total_reward": float}]` — one entry per arm, passed in as a mutable dict
- Three functions: `select_option(options, bandit_state, total_steps, exploration=1.4)`, `update_bandit(bandit_state, key, reward)`, `ensure_bandit_structure(state)`
- No classes. Fully stateless (state passed in/out). No external dependencies (stdlib `math` only).
- Domains tracked: `strategy`, `mutation`, `tool` (hardcoded in `ensure_bandit_structure`)

**`ai-lab/core/catalyst.py` — the multi-factor selector:**
- Imports bandit via `from core.policy_engine import select_option, update_bandit` (not from `bandit.py` — apparent legacy naming inconsistency)
- Implements: `choose_strategy(state)`, `get_adaptive_exploration_rate(state)`, `choose_mutation(state, previous_mutation)`, `apply_mutation(idea, mutation_type)`
- Multi-factor scoring in `choose_mutation`: `score = (base * 0.4 + chain_bonus * 0.4 + decay * 0.2) * type_penalty`
- Confidence ramp: `confidence = min(1.0, count / 10)` — ramps linearly to 1.0 over 10 pulls
- Strategy selection blends learned best (from bandit) with heuristic base using a probability formula
- Selection method: weighted random (not argmax) — `random.random()` against cumulative weights
- Has `print()` statements throughout (not primitive-shaped)
- Uses `random.random()` — not primitive-shaped (non-deterministic without seed)

The bons.ai code is proof-of-concept quality: functional but not clean, not typed, not class-based, and not extractable as-is.

---

### Q8 — What's in `pyproject.toml` / `requirements.txt`?

**ANSWERED.**

```toml
dependencies = [
    "pydantic>=2.7",
    "pyyaml>=6.0",
    "click>=8.1",
    "numpy>=2.0,<3.0",
    "sentence-transformers>=3.0",
    "fossic @ file:///home/boop/Projects/fossic/fossic-py",
]
```

No `requirements.txt`. Notable:
- **numpy is present** — available for bandit math if needed (log, sqrt)
- **No scipy, vowpalwabbit, ax-platform** — no existing ML/bandit library
- `sentence-transformers` implies numpy is load-bearing (embeddings in retrieval)
- The ai-lab bandit only uses stdlib `math` — it would not require adding numpy

---

## Section 2 — Primitive Landscape Map

| Primitive Name       | Status     | Location                            | API Surface                                                                      |
|----------------------|------------|-------------------------------------|----------------------------------------------------------------------------------|
| Clutch               | EXISTS     | `cerebra/_primitives/clutch.py`     | `Clutch.decide(signals, state) → Decision`; `Clutch.explain()` for trace        |
| Triangulator         | EXISTS     | `cerebra/_primitives/triangulator.py` | `triangulate(score, confidence, signal_strength) → float`; `triangulate_with_components()` |
| Trajectory           | EXISTS     | `cerebra/_primitives/trajectory.py` | `TrajectoryTracker.update(composite, delta) → TrajectoryState`                  |
| HysteresisModeRouter | EXISTS     | `cerebra/_primitives/mode_router.py` | `HysteresisModeRouter.decide(signals, candidate_mode) → ModeDecision`           |
| ScoreComposer        | EXISTS     | `cerebra/_primitives/score_composer.py` | `compose(components, weights) → CompositeScore`; `CompositeScore.explain()`   |
| TombstoneSet         | EXISTS     | `cerebra/_primitives/tombstone_set.py` | `TombstoneSet.add/tombstone/restore/state/get()`                              |
| Bandit (any form)    | NOT FOUND  | —                                   | No bandit primitive in `cerebra/` or `tests/`; proof-of-concept in ai-lab only  |

Additional note on Clutch: there are two objects named "Clutch" in the codebase. The primitive (`cerebra/_primitives/clutch.py`) is the generic rule-cascade primitive. The consumer (`cerebra/cognition/clutch.py`) is `ClutchEngine` — Cerebra's cycle-runtime implementation built on the same pattern but with a distinct API and no inheritance from the primitive.

---

## Section 3 — Where New Primitives Would Naturally Live

Based on Q1 and Q5:

**The consistent pattern is: primitives go in `cerebra/_primitives/`.** All six named Lattica primitives live there. No primitives live anywhere else in the tree. The `_primitives/` package is the dedicated home for this category of code.

`cerebra/cognition/` is for Cerebra-specific consumers of primitive patterns (e.g., `ClutchEngine` consuming the Clutch pattern). The re-export in `cerebra/cognition/__init__.py` makes primitives available downstream without requiring direct imports from `_primitives`.

If `_primitives_canonical/` were populated, it would be the update-first target before re-vendoring into `_primitives/`. Currently `_primitives_canonical/` is empty.

---

## Section 4 — Open Questions Surfaced

1. **Bandit primitive specification is missing.** `CEREBRA_CATALYST.md` references "lattica-primitives §Bandit Selector" as the authoritative bandit spec. No such section exists in `docs/refined-runtime-model/LATTICA_PRIMITIVES.md`. The spec must be written (or sourced from ai-lab analysis) before a primitive-shaped implementation can be contracted.

2. **The `_primitives_canonical/` directory is empty.** `VENDORED_FROM.md` says canonical copies live there; the directory contains only an empty `__init__.py`. It's unclear whether canonical copies were never written or were deleted. If the bandit is to follow the vendor-from-canonical pattern, the canonical copy would need to go there first.

3. **Naming collision: `Clutch` (primitive) vs `ClutchEngine` (consumer).** Both exist in the codebase and serve different purposes. `CEREBRA_CATALYST.md` may use "Clutch" to mean either. Step 2 kickoff should clarify which one the catalyst integrates with (answer appears to be: neither — catalyst is called when ClutchEngine escalates via `escalate_to_catalyst=True`, so the catalyst is a peer of ClutchEngine, not a child).

4. **The ai-lab bandit imports from `core.policy_engine`, not `core.bandit`.** The actual connection between `bandit.py` and `catalyst.py` in ai-lab is ambiguous (may be a renamed module). If Step 2 references ai-lab code for the bandit algorithm, this inconsistency should be resolved before extraction.

5. **Bandit arm vocabulary for Cerebra.** The ai-lab bandit tracks `strategy`, `mutation`, `tool` domains. The Cerebra catalyst selects from `CLUTCH_ACTIONS` (accept, refine, critique, etc.). These are different vocabularies. The arm vocabulary for the Cerebra bandit is unspecified in the current primitives or in `LATTICA_PRIMITIVES.md`.

6. **Five of the six primitives are currently unused by Phase 8/9 cycle runtime.** `cerebra/cognition/__init__.py` re-exports them all, but only `ScoreComposer` (via `compose`) is imported downstream (`cerebra/retrieval/scorer.py`). Trajectory, HysteresisModeRouter, TombstoneSet, and the primitive Clutch are present but not wired into the cycle runtime. This is expected per roadmap, but worth noting for Step 2 kickoff: the catalyst may be the first cycle-runtime consumer of Triangulator or Trajectory.

---

## Section 5 — Recommendations for Phase 9 Step 2 Prep

**Pending human review of audit findings before Step 2 kickoff drafted.**

The missing bandit primitive specification (Q4, Open Question 1) and the absent canonical copy (Open Question 2) are prerequisite decisions that require human judgment. The audit does not have enough information to prescribe placement or spec shape.
