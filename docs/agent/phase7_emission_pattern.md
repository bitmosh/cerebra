# Phase 7 — Safety-gated action emission pattern

## v0.1 behavior (two-state gate)

The Phase 7 gate is two-state: `"permitted"` or `"forbidden"`. The `"requires_review"`
path is deferred to v0.2 (DEV-010). Constitutional forbids always return False in v0.1
(DEV-009). Tests cover both no-op behaviors explicitly.

## Canonical emission sequence

For any cycle action that requires leeway gate approval, emission follows this exact order:

```python
from cerebra.governance import LeewayPreActionGate, ProposedAction, emit_leeway_grant_applied

# 1. Cycle runtime proposes an action (typically from Clutch decision)
proposed = ProposedAction(
    action_name=clutch_decision.action,   # maps to LeewayRule.capability
    session_id=session.session_id,
    cycle_id=cycle_id,
    step_id=step_id,
)

# 2. Gate evaluates (two-state in v0.1: "permitted" or "forbidden")
gate_decision = leeway_gate.evaluate(proposed)

# 3. CRITICAL: LeewayGrantApplied is emitted BEFORE the action event
#    (causation_id = ClutchDecisionMade event ID or CatalystArmSelected event ID)
leeway_event_id = emit_leeway_grant_applied(
    emitter,
    gate_decision,
    triggering_event_id=clutch_decision_event_id,
)

# 4. Only if permitted, emit the action event causally chained to the leeway grant
if gate_decision.final_decision == "permitted":
    action_event_id = emitter.emit_cycle_event(
        event_type="StepStarted",  # or whichever gated action
        payload={
            "step_id": step_id,
            "step_type": clutch_decision.action,
            # DEFENSIVE: include leeway_grant_event_id as a cross-reference
            # Phase 8 obligation: include this field in all gated action payloads
            "leeway_grant_event_id": leeway_event_id.hex(),
            # ... other action-specific fields
        },
        causation_id=leeway_event_id,  # explicit causal chain to leeway grant
    )
# If "forbidden": cycle handles separately — Phase 9+ Clutch territory
```

## Safety invariant

`LeewayGrantApplied` MUST be emitted BEFORE the action event it gates. The action
event's `causation_id` references the `LeewayGrantApplied` event ID, making the
causal chain auditable.

The defensive cross-reference (`leeway_grant_event_id` in action event payload) makes
the invariant structurally verifiable: a query against the action event can confirm that
the cited `LeewayGrantApplied` event:
- Exists in the same cycle stream
- Has a lower version number (emitted before the action)
- Has `final_decision == "permitted"`

**Phase 8 obligation:** All gated action event payloads must include `leeway_grant_event_id`.
This field is defined here but not yet enforced — it becomes mandatory when Phase 8 wires
the gate into the cycle action proposal path.

## Single-threaded assumption

v0.1 cycle runtime is synchronous and single-threaded per stream. Sequential emission
preserves the ordering invariant automatically. If a future phase introduces concurrent
emission to the same stream (background telemetry, agentic delegation), the ordering
discipline must be explicitly enforced via locks or batch appends. Do not introduce
concurrent emission without auditing this invariant.

## v0.2 extensions

- `"requires_review"` decision: add `requires_review_capabilities: list[str]` to
  `LeewayRule` and `requires_review()` predicate. Cycle runtime must pause and request
  HITL confirmation before emitting the gated action event.
- Constitutional pre-action blocks: add a dedicated pre-action rule shape to
  `ConstitutionalRule` (separate from the existing post-action `revokes_leeway_when`
  output analyzers). `forbids()` returns True for such rules.
