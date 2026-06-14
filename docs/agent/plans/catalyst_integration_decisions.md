# Catalyst Integration Decisions — Phase 9 Step 3

**Status:** Research doc, pre-kickoff
**Audience:** Cerebra Claude (kickoff drafter), bandit (implementing agent)
**Purpose:** Resolve the 10 concrete decisions needed before Phase 9 Step 3 CatalystEngine kickoff drafting
**Sources:** CEREBRA_CATALYST.md (spec), LATTICA_PRIMITIVES.md §11 (bandit primitive), Phase 9 Step 1 PASS COMPLETE (ClutchEngine state), CEREBRA_CATALYST.md §12 (MVP scope)

---

## Context

Phase 9 Step 1 shipped ClutchEngine with `escalate_to_catalyst` flag. Phase 9 Step 2 shipped the Bandit primitive at `cerebra/_primitives/bandit.py`. Step 3 implements the CatalystEngine consumer that consumes both: ClutchEngine's escalation signal, and the Bandit primitive's arm statistics.

Before drafting the Step 3 kickoff, ten concrete decisions need explicit resolution. This doc records them with reasoning.

---

## D1 — Persistence model: per-session SQLite

**Decision:** arm_stats persist in a new SQLite table tied to `runtime_session_id`. Within-session multi-step accumulation works; cross-session learning is explicitly deferred to v0.3+.

**Alternatives considered:**

- **In-memory only** — Catalyst instance holds arm_stats. Lost on session close. No persistence.
- **Vault-wide** — arm_stats shared across all sessions in vault. Maximum learning signal.

**Reasoning:**

CEREBRA_CATALYST.md MVP scope (v0.3+ section) explicitly states "cross-cycle catalyst learning (preferences from one cycle inform another)" is deferred. Per DEV-012, session_id == cycle_id canonical in Cerebra; so "cross-cycle" == "cross-session". v0.1 stays within-session.

In-memory only would be functionally equivalent for v0.1 (a single cycle is the unit) but wouldn't exercise the bandit primitive's `to_state` / `from_state` methods. Persisting to SQLite validates the persistence path and prepares the surface for vault-wide expansion in v0.3+.

**Schema:**

```sql
CREATE TABLE catalyst_arm_stats (
    arm_id TEXT NOT NULL,
    runtime_session_id TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    total_reward REAL NOT NULL DEFAULT 0.0,
    last_selected_step INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (arm_id, runtime_session_id),
    FOREIGN KEY (runtime_session_id) REFERENCES runtime_sessions(session_id)
);

CREATE INDEX idx_catalyst_arm_stats_session ON catalyst_arm_stats(runtime_session_id);
```

**Forward path to v0.3+:** Remove the FK constraint, change PRIMARY KEY to `(arm_id, vault_id)` or just `arm_id`. The Bandit primitive's `to_state` / `from_state` mechanism stays unchanged; the scoping rule changes.

**Migration:** Migration017 (continuing global numbering from Phase 8's Migration016).

---

## D2 — Cycle config: new `planning.adaptive.v0`

**Decision:** Ship a new cycle config at `cycles/planning.adaptive.v0.yaml` that exercises catalyst escalation. `simple.planning.v0` remains unchanged as the deterministic-cycle reference.

**Alternatives considered:**

- **Modify simple.planning.v0 to include catalyst arms** — single-config approach.
- **Add catalyst arms to multiple existing configs** — broader exercise.

**Reasoning:**

`simple.planning.v0` is the canonical regression test for the Phase 8 cycle runtime. Phase 8 integration tests assume specific event chains, specific composite scores, specific termination conditions. Adding catalyst arms changes the behavior in subtle ways (when Clutch escalates, the event chain is longer, the action choice has randomness). This breaks reproducibility for the existing tests.

A new config makes the test surface clean: simple.planning.v0 stays deterministic and regression-stable; planning.adaptive.v0 demonstrates catalyst behavior with explicit acceptance that the events vary across runs.

The two configs become useful diff: comparing simple.planning.v0 (no catalyst) vs planning.adaptive.v0 (with catalyst) on the same goal shows what catalyst adds.

**Config structure:** Same 5-step structure as simple.planning.v0 (understand_goal → draft_plan → critique_plan → refine_plan → finalize), with two additions:
- `catalyst_arms` section declaring 5-6 arms (specified in `catalyst_v0_1_arm_vocabulary.md`)
- ClutchEngine rules tuned to escalate more often (so catalyst actually fires; simple.planning.v0's rules are too "safe" — they always match the default_accept rule)

---

## D3 — Arms are strategies, not CLUTCH_ACTIONS

**Decision:** Catalyst arms represent cognitive STRATEGIES (e.g., "constraint_check", "decomposition"). Each arm has a `mapped_action` field declaring which CLUTCH_ACTION it produces when selected (usually "refine"). Catalyst returns the arm; the cycle runtime maps to action.

**Alternatives considered:**

- **Arms ARE CLUTCH_ACTIONS** — catalyst picks among accept/refine/critique/explore/branch/etc. Simpler.
- **Arms are independent of CLUTCH_ACTIONS** — catalyst returns a "strategy" with no defined action mapping; cycle runtime decides what to do.

**Reasoning:**

CEREBRA_CATALYST.md §5 explicitly shows arms as cognitive strategies (decomposition, constraint_check, exploration, refinement, etc.) — not control actions. The strategies are richer than the 10-item CLUTCH_ACTION vocabulary. Making arms strategies preserves the spec's intent.

Mapping arms to CLUTCH_ACTIONS via a field gives the runtime a clean handoff: catalyst returns an arm, runtime reads the mapped_action, cycle continues with that action plus strategy context attached. Most v0.1 arms map to "refine" since the catalyst typically fires after a step that didn't fully satisfy the rule cascade — the refinement happens with a specific strategy.

**Arm structure in YAML:**

```yaml
catalyst_arms:
  - arm_id: constraint_check
    type: verification
    mapped_action: refine
    strategy_prompt: |
      Critique the plan with focus on constraint satisfaction.
      Identify any implicit or explicit constraints that may be violated.
      Surface assumptions that need explicit verification.
  - arm_id: decomposition
    type: structuring
    mapped_action: refine
    strategy_prompt: |
      Break down complex sub-goals into more concrete sub-steps.
      Identify dependencies between sub-goals.
      Surface any sub-goals that need further decomposition.
```

The `strategy_prompt` is injected into the next step's prompt template as a "strategy hint" variable.

---

## D4 — Type categorization: explicit per-arm field, K=5 window

**Decision:** Each arm declares an explicit `type` field. The type_penalty formula uses `recent_type_count` over the last K=5 catalyst selections (per CEREBRA_CATALYST.md §3.4 default).

**Alternatives considered:**

- **Each arm is its own type** — type_penalty becomes "don't pick same arm twice in a row." Simpler but coarse.
- **Hierarchical types** — multi-level categorization. Overkill for v0.1.

**Reasoning:**

CEREBRA_CATALYST.md §5 examples show types like "exploration", "refinement", "verification" with multiple arms per type. Type_penalty fires when multiple same-type arms get picked in a row, encouraging diversity across strategy types rather than diversity across individual arms.

For v0.1 planning vocabulary, suggested types: `verification`, `structuring`, `estimation`. Each arm declares one type. The K=5 window means after 5 catalyst selections, the type_penalty calculation considers the prior 5 selections only. With ~10 catalyst invocations per session (rough estimate for v0.1 testing), this is enough samples to surface diversity behavior without being noise.

**Formula reminder** (from CEREBRA_CATALYST.md §3.4):
```
recent_type_count = count of selections of this arm's type in last K selections
type_penalty = max(0.5, 1.0 - (recent_type_count × type_pressure))
type_pressure default: 0.15
```

So 0 recent same-type = 1.0 (no penalty). 1 recent = 0.85. 2 recent = 0.7. 3 recent = 0.55. 4+ recent floored at 0.5.

---

## D5 — Event chain causation

**Decision:** The catalyst-side event chain extends the existing Clutch chain:

```
ClutchDecisionMade (escalate_to_catalyst=True)
  ↓ causation_id
CatalystInvoked
  ↓ causation_id
CatalystArmSelected
  ↓ causation_id
(next step's StepStarted, which uses arm's strategy_prompt)
```

**Reasoning:**

Causation chains track decision provenance. ClutchDecisionMade is the trigger (Clutch chose to escalate). CatalystInvoked is the response (catalyst was called). CatalystArmSelected is the outcome (specific arm chosen). The next step's StepStarted carries forward the causation from the arm selection.

When a step uses an arm's strategy_prompt, StepStarted's event payload includes:
```json
{
  "strategy_arm_id": "constraint_check",
  "strategy_arm_type": "verification",
  "causation_id": "<CatalystArmSelected event_id>"
}
```

This makes the trace queryable: "show me all steps influenced by constraint_check strategy" or "show me the cascade from this Clutch escalation."

CatalystInvoked payload (per fossic AGENT_TRACE_VOCABULARY §7.6.1 or wherever Catalyst events live — verify the section number):
```json
{
  "session_id": "...",
  "cycle_id": "...",
  "step_id": "...",
  "clutch_decision_id": "...",
  "available_arms": ["constraint_check", "decomposition", "risk_assessment", ...],
  "invoked_at": 1718000000000
}
```

CatalystArmSelected payload:
```json
{
  "session_id": "...",
  "cycle_id": "...",
  "step_id": "...",
  "catalyst_invocation_id": "...",
  "selected_arm_id": "constraint_check",
  "selected_arm_type": "verification",
  "mapped_action": "refine",
  "arm_score": 0.72,
  "score_components": {
    "base_reward": 0.65,
    "type_penalty": 0.85,
    "confidence_ramp": 0.4
  },
  "sampled_at": 1718000000000
}
```

---

## D6 — Cannot-select handling

**Decision:** When catalyst cannot select an arm (no arms eligible after filtering, empty arm vocabulary, all arms forbidden in future leeway integration), emit `CatalystArmSelected` with `selected_arm_id: null` and `reason: "cannot_select"`. Cycle falls back to Clutch's default action (the action that was set on ClutchDecision before escalation, usually "accept").

**Reasoning:**

The phase6 thesis v2 step 10 explicitly notes "If filtered set empty: cannot_select → Clutch safe default." This is the explicit fallback path. Emitting the event with null arm preserves the trace (we know catalyst tried and failed) while letting the cycle proceed.

For v0.1, the only way catalyst can't select is empty arm vocabulary (no arms declared in cycle config). Future leeway-catalyst integration (v0.2 per MVP scope) introduces leeway-based filtering; cannot_select becomes more meaningful then.

---

## D7 — Reward feedback timing

**Decision:** After catalyst selects arm at step N, the cycle proceeds to execute step N+1 using the arm's strategy. The reward for that arm is computed at step N+1's evaluation phase:

```
reward = composite × confidence × signal_strength
```

(same triangulator formula as CEREBRA_CATALYST.md §10).

The reward is sent to `Bandit.update(arm_id, reward)` immediately after the EvaluationComposed event for step N+1, before step N+2 starts.

**Reasoning:**

This matches the spec's "After every catalyst selection, the cycle evaluates the resulting step and computes a reward. That reward updates the arm stats."

Open edge case: what if the cycle terminates after step N+1 (stop condition, max steps, accept outcome) before another catalyst invocation? The arm_stats for the selected arm get the reward; they just won't influence future selections in this session. Fine for v0.1.

Open edge case 2: what if catalyst fires multiple times within one step's evaluation cycle (Clutch escalates, catalyst returns "refine", evaluation runs, Clutch escalates again)? Per Phase 8 design, Clutch evaluates once per step. So catalyst fires at most once per step. This edge case shouldn't arise in v0.1.

---

## D8 — Engine placement: `cerebra/cognition/catalyst.py`

**Decision:** CatalystEngine lives in `cerebra/cognition/catalyst.py`. Class name: `CatalystEngine`.

**Reasoning:**

Matches the pattern from Phase 9 Step 1: ClutchEngine consumer is at `cerebra/cognition/clutch.py`, separate from the Clutch primitive at `cerebra/_primitives/clutch.py`. CatalystEngine should mirror this: consumer at `cerebra/cognition/catalyst.py`, consuming the Bandit primitive at `cerebra/_primitives/bandit.py`.

The cognition/ namespace is where Cerebra-specific runtime consumers live; _primitives/ is generic and reusable. Both layers stay distinct.

---

## D9 — Schema details for catalyst_arm_stats

**Migration017** specifics:

```sql
CREATE TABLE catalyst_arm_stats (
    arm_id TEXT NOT NULL,
    runtime_session_id TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    total_reward REAL NOT NULL DEFAULT 0.0,
    last_selected_step INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (arm_id, runtime_session_id),
    FOREIGN KEY (runtime_session_id) REFERENCES runtime_sessions(session_id)
);

CREATE INDEX idx_catalyst_arm_stats_session ON catalyst_arm_stats(runtime_session_id);

-- Track recent selections for type_penalty (last K window)
CREATE TABLE catalyst_recent_selections (
    runtime_session_id TEXT NOT NULL,
    selection_order INTEGER NOT NULL,  -- monotonic per session, sortable
    arm_id TEXT NOT NULL,
    arm_type TEXT NOT NULL,
    selected_at INTEGER NOT NULL,
    PRIMARY KEY (runtime_session_id, selection_order),
    FOREIGN KEY (runtime_session_id) REFERENCES runtime_sessions(session_id)
);

CREATE INDEX idx_catalyst_recent_session_order ON catalyst_recent_selections(runtime_session_id, selection_order DESC);
```

Two tables: `catalyst_arm_stats` (cumulative per-arm) and `catalyst_recent_selections` (rolling window for type_penalty calculation).

**Why two tables:** type_penalty needs to know the last K selections in order. Could be computed from `last_selected_step` ordering across all arms, but a dedicated recent-selections table is simpler and cheaper to query. Plus it cleanly handles the case where multiple arms have the same `last_selected_step` (shouldn't happen but defensive).

**Cleanup:** No explicit cleanup of `catalyst_recent_selections` — old rows are tied to closed sessions and naturally become inert. Optional `VACUUM` or periodic cleanup in v0.2+.

---

## D10 — v0.1 leeway integration: NOT integrated

**Decision:** Per CEREBRA_CATALYST.md MVP scope, v0.1 catalyst does NOT integrate with the leeway network. All declared arms in the cycle config are eligible for selection. Leeway-catalyst integration ships in v0.2.

**Reasoning:**

CEREBRA_CATALYST.md §12 explicitly lists "Catalyst integration with leeway network filter" as v0.2 deferral. v0.1 catalyst is the algorithmic mechanism; leeway integration adds safety constraints on top.

For v0.1, the catalyst sees all declared arms and selects via the 3-factor scoring (`base_reward × type_penalty × confidence_ramp`, with `chain_bonus × decay_factor` deferred). The leeway gate continues to operate on actions emitted by the cycle (memory_write, branch_creation, etc.) — but catalyst arm selection is upstream of action emission, so leeway has no v0.1 role.

This decision simplifies v0.1 implementation: no LeewayCatalystFilter, no per-arm leeway evaluation, no "cannot_select due to leeway" branch.

---

## Summary of decisions

| # | Decision | Rationale source |
|---|---|---|
| D1 | Per-session SQLite persistence | CEREBRA_CATALYST.md MVP scope (cross-cycle = v0.3+) |
| D2 | New `planning.adaptive.v0` config | Preserve simple.planning.v0 as regression baseline |
| D3 | Arms are strategies, mapped to CLUTCH_ACTIONS | CEREBRA_CATALYST.md §5 examples |
| D4 | Explicit per-arm `type` field, K=5 window | CEREBRA_CATALYST.md §3.4 defaults |
| D5 | Causation chain Clutch → Catalyst → Step | Standard fossic causation pattern |
| D6 | Cannot-select → null arm + Clutch default | Phase 6 thesis v2 step 10 |
| D7 | Reward computed at N+1 evaluation | CEREBRA_CATALYST.md §10 |
| D8 | CatalystEngine at `cerebra/cognition/catalyst.py` | Mirror Phase 9 Step 1 ClutchEngine placement |
| D9 | Two tables: arm_stats + recent_selections | Type_penalty efficient calculation |
| D10 | No v0.1 leeway integration | CEREBRA_CATALYST.md MVP v0.2 deferral |

---

## Open items for Step 3 kickoff

Things still requiring decision DURING implementation, not before:

1. **Specific event payload field names** — verify against fossic AGENT_TRACE_VOCABULARY when bandit implements (the field names I suggested above are best-effort; actual canonical naming should match fossic conventions when the events get added to vocab spec)

2. **Arm score normalization** — the 3-factor formula produces unbounded scores in theory; weighted-random sampling needs normalized weights. Per CEREBRA_CATALYST.md §4, the catalyst computes per-arm scores then normalizes for weighted sampling. The normalization happens at sampling time, not score time.

3. **Reward bounding** — composite is [0,1], confidence is [0,1], signal_strength is [0,1]. Their product is [0,1]. Good — reward fed to Bandit.update() stays in [0,1] range.

4. **Cycle config validation** — when loading planning.adaptive.v0, validator should confirm: catalyst_arms is non-empty; each arm has required fields (arm_id, type, mapped_action, strategy_prompt); mapped_action is a valid CLUTCH_ACTION; arm_ids are unique within the config.

5. **Rule tuning for planning.adaptive.v0** — the cycle's Clutch rules need to escalate more often than simple.planning.v0's rules. Specific rule changes specified in `catalyst_v0_1_arm_vocabulary.md`.
