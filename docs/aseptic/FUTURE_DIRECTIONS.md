---
title: Cerebra Future Directions — Living Report
last_reviewed: v0.4.0 (Phase 9 close + Lattica round-3 coordination)
---

# Cerebra Future Directions — Living Report

Concept-stage exploration. Architectural directions documented but not yet implemented. The key distinction from TECH_DEBT: future directions don't have functional-but-bad code; they have well-formed concepts awaiting implementation.

The key test: *"is this an architectural direction we want to pursue, and do we know when implementation should begin?"*

See `docs/aseptic/LIVING_REPORTS.md` for entry format conventions. Note: FUTURE_DIRECTIONS.md entries use the FD- prefix to distinguish from TECH_DEBT (TD-) and POLISH_DEBT (PD-) IDs.

---

## Open entries

### FD-001 — Dark matter substrate implementation

**What it is:** The "dark matter" substrate concept (banked from concept exploration) represents implicit context that influences cognition but isn't explicitly retrieved — analogous to ambient background knowledge.

**Why it's deferred:** Conceptual work; no implementation surface in v0.1. v0.1 retrieval is explicit-only.

**Known cost:** None at v0.1. Future cognitive extensions may need this substrate to handle ambient priors and tacit knowledge.

**Trigger:** Post-v0.1 cognitive extension work begins (specifically, when Phase 9+ cycle configs need implicit context handling).

**Evidence:** `event_sourced_cognitive_substrate.md`, concept docs in `docs/agent/concepts/`.

---

### FD-002 — Witness layer projections (lattica-es aggregate consumer)

**What it is:** The witness layer is the v0.2 cognitive observation mechanism — subscribes to fossic streams, projects cognitive state, surfaces patterns for retrospective analysis. v0.1 ships cycle event emission but no consumer of those streams.

**Why it's deferred:** v0.1 milestone targets cycle runtime functionality. Witness layer is post-v0.1.

**Known cost:** Events emit to fossic streams but no projections consume them yet. Stream data accumulates without analysis surface.

**Trigger:** v0.2 work begins, OR a specific cognitive observation need surfaces during v0.1 usage.

**Evidence:** `event_sourced_cognitive_substrate.md`, Phase 8 close artifacts.

---

### FD-003 — Counterfactual cognition via branching (cognitive use)

**What it is:** Phase 8 ships the branching mechanism (fossic supports branches; LeewayGrantApplied gates branch_creation). But no cycle in v0.1 actually triggers branching for counterfactual exploration. The mechanism is ready; the cognitive use isn't.

**Why it's deferred:** v0.1 cycle configs (simple.planning.v0) are linear. Branching for counterfactual cognition requires more sophisticated cycle configs and Clutch decision logic that Phase 9 ships.

**Known cost:** Branching capability exists but unused. No observable cost at v0.1; capability waits for post-v0.1 cognitive extensions.

**Trigger:** Post-v0.1 cycle config design includes counterfactual exploration (branch action in Clutch decision tree).

**Evidence:** Phase 7 leeway gate action vocabulary, Phase 8 design doc §7.

---

### FD-004 — Cognitive extensions (lenses, frame, methodology, iterative self-improvement)

**What it is:** Five concept documents in `docs/agent/concepts/` describe cognitive extensions: interpretive lattice, archetypal lenses, evaluative frame, iterative self-improvement, cognitive extension overview. ~15,600 words of architectural exploration. None implemented in v0.1.

**Why it's deferred:** v0.1 ships the cognitive runtime substrate. Cognitive extensions live on top of that substrate; they're post-v0.1.

**Known cost:** Substantial conceptual work exists without implementation grounding. Some concepts may need revision when implementation surfaces.

**Trigger:** Post-v0.1 milestone reached AND specific extension prioritized based on real-world usage gaps.

**Evidence:** `docs/agent/concepts/interpretive_lattice.md`, `archetypal_lenses.md`, `evaluative_frame.md`, `iterative_self_improvement.md`, `cognitive_extension_overview.md`.

---

### FD-005 — `ActionProposed` event: cross-stream causation anchor for external gates

**What it is:** When Cerebra submits a command to an external evaluator
(policy-scout, Phase 2), it must emit an `ActionProposed` event on the parent
`cerebra/agent-trace/<cycle_id>` stream as the cross-stream causation root.
Policy-scout's `CommandRequested` event references `ActionProposed.event_id`
as its `causation_id`, enabling `fossic.walk_causation` to trace the full
`Cerebra → policy-scout` chain.

**Confirmed payload (Lattica/policy-scout round-3, 2026-06-14):**
```json
{
  "session_id": "string",
  "cycle_id": "string",
  "step_id": "string",
  "proposed_action": "string",
  "proposed_to": "string ('policy_scout' | 'leeway_gate')",
  "proposed_at": "int (Unix epoch milliseconds)"
}
```

**Why it's deferred:** Policy-scout fossic integration is Phase 2. The
causation chain cannot be wired until both sides have fossic emitters.
Introducing `ActionProposed` simultaneously with the fossic emitter landing
in v0.2 is the correct moment.

**Known cost:** Until this event exists, cross-stream causation traces from
policy-scout decisions back to Cerebra's cycle context are impossible.
Internal causation (`CycleRuntime` → `LeewayGrantApplied`) is unaffected.

**Trigger:** Cerebra v0.2 / Phase 2 policy-scout integration begins.

**Evidence:** Lattica coordination rounds 2a and 3 (2026-06-14), joint
causation convention round with policy-scout Claude.

---

### FD-006 — `ReinjectionBlocked` event + `evaluate()` predicate-first restructure

**What it is:** Two related v0.2 changes:

1. **Restructure `ReinjectionTriggerEvaluator.evaluate()`** — move the depth
   check AFTER predicate evaluation (currently depth check is a pre-loop
   short-circuit at line 97 of `reinjection.py`). This guarantees that when
   the depth limit blocks re-injection, we know which predicate would have
   fired.

2. **Emit `ReinjectionBlocked` event** on the parent stream when
   `recursion_depth >= max_recursion_depth` blocks a predicate that would
   otherwise have fired. Makes terminal chain nodes observable from fossic
   alone, without cross-DB queries into `cerebra.db`.

**Confirmed payload (Lattica round-3, 2026-06-14):**
```json
{
  "session_id": "string",
  "cycle_id": "string",
  "recursion_depth": "int",
  "max_recursion_depth": "int",
  "trigger_predicate": "string",
  "blocked_at": "int (Unix epoch milliseconds)"
}
```

`trigger_predicate` is non-null after the restructure — the predicate always
matches before the depth check applies (given option (a) evaluation order).

**Why it's deferred:** No v0.1 tile requires it; no consumer exists until
R-CB-003 (Lattica session chain visualization, queued v0.2.0).

**Known cost:** Terminal chain nodes (cycles blocked by depth limit) are
unobservable from fossic in v0.1. Lattica's R-CB-003 tile cannot distinguish
"chain complete" from "chain depth-limited" without this event.

**Trigger:** Cerebra v0.2 / Lattica R-CB-003 tile implementation begins.

**Evidence:** Lattica coordination rounds 2a and 3 (2026-06-14). Implementation:
5-line reorder in `cerebra/cognition/reinjection.py::ReinjectionTriggerEvaluator.evaluate()`.

---

## Resolved entries

(none yet — Phase 8 close is the first formal review)

---

*Migration note: FD-001 through FD-004 originated as TD-004 through TD-007 in TECH_DEBT.md (Phase 8 close seeding). Moved to this file in v0.3.6 cleanup pass after methodology review determined they fit the FUTURE_DIRECTIONS category (concept-stage exploration) rather than TECH_DEBT (functional but known-bad implementation). Content preserved verbatim except for ID prefix change.*

*Last reviewed at v0.3.6 cleanup. Next review: when any FD entry's trigger condition fires, or supervisor pass.*
