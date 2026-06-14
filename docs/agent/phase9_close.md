# Phase 9 Close Summary

Phase 9 built the adaptive cognitive control layer: a stateful predicate cascade (Clutch),
bandit-driven strategy selection (Catalyst/BanditSelector), and cycle-to-cycle continuation
via re-injection. Together with Phase 8's cycle runtime, these form Cerebra's complete v0.1
cognitive loop.

---

## What shipped

### Step 1 — Full ClutchEngine (v0.3.6 partial)

- `ClutchEngine` replacing `ClutchStubEngine` — 7 new predicates, cascade depth tracking,
  `escalate_to_catalyst` flag, `ClutchCycleState` accumulator
- `ClutchDecision.cascade_depth: int` — observability for rule-ordering debugging
- `CycleConfig.composite_floor: float = 0.3` — per-cycle Clutch floor configuration
- `catalyst_was_invoked` predicate stub — registered for config validation, placeholder impl
- `pass-9.1.md` cross-pollination — `ClutchDecisionMade` payload extension to fossic
- `docs/agent/deviations/v0.3.6.md` — DEV-025 through DEV-030

### Step 2 — BanditSelector primitive (v0.3.6 continuing)

- `cerebra/_primitives/bandit.py` — seventh vendored Lattica primitive; UCB-based multi-armed
  bandit with `ArmStats`, `BanditSelection`, `Bandit` class, `ensure_arms()`, `select()`,
  `record_reward()`, `get_stats()`, `to_state()`, `from_state()`
- `VENDORED_FROM.md` updated; `_primitives/__init__.py` and `cognition/__init__.py` updated
- `docs/agent/deviations/v0.3.6.md` — DEV-031, DEV-032

### Step 3 — CatalystEngine consumer (v0.3.6 continuing)

- `cerebra/cognition/catalyst.py` — `CatalystEngine` wrapping `BanditSelector`; 3-factor
  scoring (`base_reward × type_penalty × confidence_ramp`); persistence to two new SQLite
  tables; `CatalystSelection` dataclass
- `Migration017_CatalystArmStats` — `catalyst_arm_stats` + `catalyst_recent_selections` tables
- `cycles/planning.adaptive.v0.yaml` — new cycle config exercising catalyst escalation;
  5 strategy arms (constraint_check, decomposition, risk_assessment, prerequisite_id,
  resource_estimate); no `default_accept` rule so moderate composites escalate to catalyst
- `CycleRuntime` wired to invoke `CatalystEngine` when `escalate_to_catalyst=True`
- `pass-9.3.md` cross-pollination — `CatalystInvoked` + `CatalystArmSelected` payload schemas
- `docs/agent/deviations/v0.3.6.md` — DEV-033, DEV-034, DEV-035
- `CatalystArmSelected.score_components` fix (Step 3 catchup) — field was populated in
  `CatalystSelection` but not included in emit payload; one-line fix at Step 3 close

### Step 3 catchup — pass-9.3.md + TD-018/019 + research doc corrections

- `pass-9.3.md` — accurate payload schemas from actual code; 6 field-name divergences from
  D5 planning spec documented; `score_components` gap flagged (later fixed)
- `TD-018` — CliRunner `mix_stderr=False` compat, 39 pre-existing failures
- `TD-019` — `test_lattice_against_vault.py` vault-disk failure, unknown root cause
- `catalyst_v0_1_arm_vocabulary.md` — `floor` param removed from `consecutive_steps_below_floor`;
  `refine_plan` template corrected from `prior_steps[N].output` to `prior_step_output`
- `catalyst_integration_decisions.md` — D11 added (`role: str = ""` on CycleStep)
- `docs/agent/deviations/v0.3.6.md` — DEV-036 (score_components omission)

### Step 4 — Re-injection trigger + Phase 9 close (v0.3.6 final)

- `cerebra/cognition/reinjection.py` — `ReinjectionTriggerEvaluator`, `ReinjectionDecision`,
  `_pred_max_steps_without_acceptance`, `BUILTIN_REINJECTION_PREDICATES`
- `_constants.py` — `BUILTIN_REINJECTION_PREDICATE_NAMES`
- `cycle_config.py` — `ReinjectionTrigger` dataclass; `CycleConfig.reinjection_triggers`
  and `CycleConfig.max_recursion_depth` fields; validation rules 9 + 10
- `catalyst.py` — `parent_session_id: str | None = None` on `CatalystEngine.__init__`;
  `_fetch_arm_stats()` helper with parent fallback for arm_stats inheritance
- `cycle_runtime.py` — `CycleResult.child_result` field; `_try_reinject()` method;
  `CatalystEngine` construction passes `session.parent_session_id`
- `planning.adaptive.v0.yaml` — `max_recursion_depth: 3` + `reinjection_triggers` section
- `TD-016` resolved — `ContinuationBundle` mechanism now fully consumed
- `pass-9.4.md` cross-pollination — `ReinjectionTriggered` payload schema
- `docs/agent/deviations/v0.3.6.md` — DEV-037 through DEV-040

---

## What Phase 9 found pre-existing (not introduced)

- `Migration014_Sessions` already had `parent_session_id`, `recursion_depth`,
  `max_recursion_depth` columns. The kickoff brief described "Migration018" but the work had
  been done in Phase 8 Step 1. No new migration was needed (DEV-037).
- `SessionManager.open_session(parent_session_id=...)` already handled child session creation
  with depth tracking and `can_recurse` guard.
- `ReinjectionTriggered` and `ContinuationBundleCreated` were already registered in
  `PHASE_6_EVENT_TYPES` — vocabulary pre-populated in Phase 8.

---

## Test trajectory

| Milestone | Passing | Failing (pre-existing) | Notes |
|---|---|---|---|
| Phase 8 close (v0.3.5a) | 1590 | 40 | TD-018/019 pre-date Phase 8 |
| Phase 9 Step 1 close (v0.3.6 partial) | ~1620 | 40 | ClutchEngine + new predicates |
| Phase 9 Step 2 close | ~1680 | 40 | BanditSelector primitive |
| Phase 9 Step 3 close | ~1724 | 40 | CatalystEngine + planning.adaptive.v0 |
| Phase 9 Step 4 close (v0.3.6 final) | ~1748 | 40 | +24 reinjection unit tests |

The 40 pre-existing failures are all pre-Phase 9 and divide into:
- TD-018: 39 tests — `CliRunner mix_stderr=False` compat across 3 test files
- TD-019: 1 test — `test_lattice_against_vault.py` vault-disk unknown failure

Note: `tests/integration/test_reinjection_e2e.py` (10 tests) could not be collected in
this environment because the `fossic` PyO3 binary isn't built. This is consistent with
all other integration tests that import from `cerebra.cognition.cycle_runtime` (which
chains to `fossic` via `FossicStore`). These tests would run in an environment with
fossic installed.

---

## Debt opened in Phase 9

| ID | What | Trigger |
|---|---|---|
| TD-018 | CliRunner `mix_stderr=False` compat (39 failures) | Click version upgrade or cleanup pass |
| TD-019 | `test_lattice_against_vault.py` vault-disk failure | Adjacent vault test infra changes |

TD-016 closed this phase (ContinuationBundle mechanism now consumed).

---

## Cross-pollination files produced

| File | Severity | Content |
|---|---|---|
| `pass-9.1.md` | NEEDS-AWARENESS | `ClutchDecisionMade` payload extension |
| `pass-9.3.md` | NEEDS-AWARENESS | `CatalystInvoked` + `CatalystArmSelected` payload schemas |
| `pass-9.4.md` | NEEDS-AWARENESS | `ReinjectionTriggered` payload schema |

All three notify fossic of Cerebra event vocabulary additions/corrections for
`AGENT_TRACE_VOCABULARY.md §7`.

---

## Key architectural decisions banked

**D-Step4-1 (=S4-D1):** ReinjectionTriggerEvaluator runs AFTER cycle termination, not
during. Clutch (per-step) and re-injection (per-cycle) are orthogonal; the CLUTCH_ACTIONS
vocabulary does not need a "recurse" action.

**D-Step4-2 (=S4-D2):** Child session inherits parent's bandit arm_stats at spawn via
fallback load in `CatalystEngine._load_bandit_state()`. Stats accumulate to child's own
session_id independently thereafter.

**D-Step4-3 (=S4-D7):** Single `ReinjectionTriggered` event covers both trigger decision
and child spawn. No event emitted when depth limit blocks the trigger.

**D-Step4-4:** Synchronous child spawn (parent terminates → child runs inline). V0.2 may
async-queue child execution; the current design is correct for single-user CLI use.

---

## Methodology lessons banked

**1. "Pre-check the audit, not just the code."** The kickoff brief described Migration018
as new work. The audit found it already done in Migration014. Reading the brief as a
checklist without verifying each claim against the actual codebase would have produced a
redundant migration that would fail at runtime (table already modified). Evidence-before-fix
applies to kickoff briefs as much as to bug reports.

**2. "Pre-implementation planning docs rot at field granularity."** pass-9.3.md demonstrated
that D5's payload field names diverged from the implementation in 6 places. The cross-pollination
workflow (read code, not spec) caught all of them. Specs are intentions; emission sites are truth.

**3. "Small omissions survive review without the right instrument."** `score_components` was
in the dataclass, in the D5 spec, and on the object at emission time. It still shipped missing
from the payload in Step 3 — discovered only during the catchup review pass. The cross-pollination
format (exhaustive field list extracted from code) is the instrument that catches these.

**4. "PASS COMPLETE format is load-bearing; its prominence matters."** The delimiter
`── PASS COMPLETE · vX.X.X · YYYY-MM-DD ──` is the bumper trigger. Using wrong delimiters or
non-canonical field names would silently break the bump pipeline. The format checklist in
kickoff briefs exists for this reason — honor it, not just when the format feels unfamiliar.

**5. "Backward compatibility via optional fields, not migration."** `parent_session_id: str | None = None`
on `CatalystEngine.__init__`, `child_result: CycleResult | None = None` on `CycleResult`,
`reinjection_triggers: list = []` and `max_recursion_depth: int = 0` on `CycleConfig` — all
new capabilities added without breaking existing callers. Where possible, new features should
arrive as opt-in additions, not structural changes.

---

## Phase 10 agenda

- **Consolidation** — bridge `cycle_episode_records` → `memory_records` for retrieval-active
  state. Closes TD-015. Main deliverable of Phase 10.
- **`cerebra run-cycle` CLI entry point** — library-only today; Phase 10 exposes it.
- **`cerebra/lattice/*` vocabulary publication** — vocabulary addendum doc for the lattice
  stream event types. Currently written but not formalized.

Phase 10 version: v0.3.7. After Phase 10, v0.1 milestone is within reach pending Phase 11
(graph export to LumaWeave).
