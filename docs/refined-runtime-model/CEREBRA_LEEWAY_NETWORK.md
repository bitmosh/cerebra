# Cerebra — Leeway Network

## 1. Purpose

The leeway network is Cerebra's permissions-shaped safety architecture.

Standard safety frameworks define what's *forbidden*; everything else happens by default. The action space shrinks with each new rule. Eventually rules interact in ways nobody predicted and the agent becomes paralyzed or behaves unpredictably under composed constraints.

The leeway network inverts this. It defines what's *permitted under what conditions*. The action space grows with each permission. Adding a new permission cannot restrict other permissions because permissions compose by union, not by negation.

Inside the capability-bounded region defined by the leeway network, the cycle runtime has full cognitive freedom. The clutch is a behavioral policy, not a safety mechanism. The catalyst can mutate aggressively. Prediction-error learning can push behavior in any direction. The freedom is preserved because safety lives in the structure of what capabilities exist, not in runtime checks that interfere with each other.

This document defines the leeway rule schema, the consultation protocol (pre-action gate + post-action audit), the constitutional revocation layer, the integration with the cycle runtime and catalyst, and the MVP scope.

---

## 2. Core Doctrine

The leeway network should be:

```text
permissions-shaped (grants, not prohibitions)
capability-bounded (safety is structural, not procedural)
constitutionally-revocable (small inviolable layer above the network)
non-interfering (rules compose by union, not by precedence)
explainable (every grant or revocation has a stated reason)
auditable (consultation produces inspectable trace)
two-phase (pre-action gate + post-action audit)
declarative (rules are data, not code)
```

The leeway network is not a substitute for capability-based architecture. It operates *on top of* capability bounds. If the system has no shell-exec adapter, no leeway rule can grant shell exec — the capability doesn't exist to grant. Leeway operates within the space of capabilities the system actually has.

---

## 3. The Composition Property

This is the load-bearing property that makes the network work.

In a prohibition model, two rules can contradict ("never do X" + "always do X under condition Y"). Resolution requires priority arbitration and exception handling. Over time, the system accumulates an unmanageable resolution layer.

In a leeway model, two rules cannot contradict by construction. Both rules grant capabilities under conditions. If both conditions hold, the agent has both capabilities. If only one holds, the agent has that one. If neither, the agent has neither.

```text
There is no contradiction — there is just the union of currently-granted capabilities.
```

This is the same property that makes capability-based security work in operating systems. You can hand out a million capabilities without them interfering because *adding a capability never removes another capability*.

The leeway network can grow large without the network's rules interfering with each other. Density of guardrails does not produce procedural interference because the guardrails are not procedural.

---

## 4. The Stack

Cerebra's safety architecture stacks five layers, each typed differently and composed differently. They do not interfere because they are not the same kind of thing.

```text
┌──────────────────────────────────────────────────────────┐
│ Constitutional Layer (5-10 hard rules)                   │  inviolable
├──────────────────────────────────────────────────────────┤
│ Capability Bounds (what adapters/storage exist)          │  structurally enforced
├──────────────────────────────────────────────────────────┤
│ Truth Tower Structural Rules (tier constraints)          │  derivation discipline
├──────────────────────────────────────────────────────────┤
│ Leeway Network (conditional permissions)                 │  the focus of this doc
├──────────────────────────────────────────────────────────┤
│ Clutch Policy (what's preferred in current state)        │  behavioral
├──────────────────────────────────────────────────────────┤
│ Catalyst Defaults (what's tried under uncertainty)       │  exploratory
└──────────────────────────────────────────────────────────┘
```

The constitutional layer is the ceiling. Capability bounds are the floor. The leeway network operates in the middle, with the clutch and catalyst sitting inside the leeway-bounded space.

---

## 5. Leeway Rule Schema

A leeway rule grants a capability under conditions.

```json
{
  "rule_id": "lr_abc123",
  "schema_version": 1,
  "capability": "mutate_strategy_weights",
  "conditions": [
    {"signal": "failure_streak", "op": ">=", "value": 2},
    {"signal": "trajectory", "op": "==", "value": "degrading"}
  ],
  "condition_join": "AND",
  "scope": "current_cycle",
  "override_priority": 5,
  "revocation_conditions": [
    {"signal": "user_paused", "op": "==", "value": true}
  ],
  "phase": "pre_action",
  "reason": "Allow strategy mutation when current strategy is failing repeatedly",
  "created_at": 1717459200,
  "created_by": "system_default"
}
```

### Field semantics

```text
capability             string identifier matching what the system knows how to do
conditions             list of signal predicates that must hold
condition_join         AND | OR — how multiple conditions combine
scope                  current_step | current_cycle | current_session | persistent
override_priority      higher priorities win when multiple grants conflict on same capability
revocation_conditions  unilateral revocation triggers; if any fires, grant is void
phase                  pre_action | post_action | both — when this rule is consulted
reason                 human-readable explanation for the grant
```

### Scope semantics

```text
current_step:     grant valid only for the current cycle step
current_cycle:    grant valid for the duration of the active cycle
current_session:  grant valid until the session ends
persistent:       grant valid indefinitely (subject to revocation)
```

### Override priority semantics

When multiple rules grant the same capability with different conditions, all that match contribute. The grant is *the union of permitted variants*. Priority only matters when grants conflict on *constraints attached to* the capability (e.g., one grant allows mutation up to 0.2 magnitude, another allows up to 0.5 — the higher-priority one wins).

---

## 6. The Constitutional Layer

Constitutional rules are the few inviolable principles. They do not grant capabilities; they *revoke* leeway grants under specified conditions.

```json
{
  "rule_id": "const_001",
  "description": "Do not assist with creating weapons capable of mass casualties.",
  "revokes_leeway_when": [
    {"output_topic_in": ["cbrn_weapons", "mass_violence_planning"]}
  ],
  "applies_to": "all_capabilities",
  "is_inviolable": true,
  "created_at": 1700000000
}
```

```json
{
  "rule_id": "const_002",
  "description": "Do not claim subjective experience or consciousness.",
  "revokes_leeway_when": [
    {"output_contains_claim": "sentience"},
    {"output_contains_claim": "consciousness"},
    {"output_contains_claim": "subjective_experience"}
  ],
  "applies_to": "all_capabilities",
  "is_inviolable": true
}
```

### Constitutional Discipline

Constitutional rules must satisfy three properties:

```text
1. Few in number (5-10 maximum)
2. Articulated at the right level of abstraction
3. Auditable by external review
```

Every additional constitutional rule increases interference risk. If the constitutional layer has 30 rules, it is a procedural-safety system wearing different clothes.

The constitutional layer operates *on the leeway network*, not on actions directly. Constitutional rules don't say "never do X" — they say "any leeway grant that would permit X is automatically revoked when X-conditions are present."

This keeps the constitutional layer tiny while letting the leeway network grow as large as needed.

---

## 7. The Consultation Protocol

Leeway consultation happens in two phases.

### 7.1 Pre-Action Gate (Phase 1)

```text
Action requested by cycle runtime or catalyst
  -> leeway network filter:
       for each candidate capability, check matching leeway grants
       remove candidates that have no grant
       remove candidates whose grants are currently revoked
  -> filtered candidate set returned to caller
  -> if empty: action.cannot_proceed signal raised
       clutch falls back to next-best action or safe default
```

Pre-action gating answers: *does the system currently have permission to do this kind of thing?*

### 7.2 Post-Action Audit (Phase 2)

```text
Action completes and produces output
  -> leeway network audit:
       evaluate output against revocation conditions of any applied grant
       evaluate output against constitutional layer revocation conditions
  -> if revocation triggers:
       rollback if action is reversible
       quarantine output if action is not reversible
       log incident with full audit trace
       update calibration on triggering rule
```

Post-action audit answers: *given what was actually produced, did the system violate any constraint?*

### 7.3 Why Both Phases

Pre-action checks are cheap and prevent the wrong *kind* of action from running at all. Post-action checks are expensive but can evaluate the actual *content* of what was produced.

Some constraints are knowable pre-action (capability gating). Some are only knowable post-action (content evaluation). Trying to collapse to one phase produces worse failure modes than implementing both.

Each leeway rule declares its phase:

```text
phase: pre_action     consulted only at the gate
phase: post_action    consulted only at the audit
phase: both           consulted at both phases (rare; for edge cases)
```

Default for capability-shaped rules: pre_action. Default for content-shaped rules: post_action.

---

## 8. Concrete Examples

### 8.1 Mutation Permission

```json
{
  "capability": "mutate_strategy_weights",
  "conditions": [
    {"signal": "failure_streak", "op": ">=", "value": 2},
    {"signal": "trajectory", "op": "==", "value": "degrading"}
  ],
  "condition_join": "AND",
  "scope": "current_cycle",
  "phase": "pre_action",
  "reason": "Strategy mutation is risky; permitted only when current strategy is clearly failing"
}
```

### 8.2 Truth Tower Promotion

```json
{
  "capability": "promote_to_truth_tower_T4",
  "conditions": [
    {"signal": "cross_validation_count", "op": ">=", "value": 2},
    {"signal": "confidence", "op": ">=", "value": 0.7}
  ],
  "condition_join": "AND",
  "scope": "current_session",
  "phase": "pre_action",
  "revocation_conditions": [
    {"signal": "contradiction_detected_among_supports", "op": "==", "value": true}
  ],
  "reason": "T4 promotion requires cross-validation and reasonable confidence"
}
```

### 8.3 Continuation Spawn

```json
{
  "capability": "spawn_continuation_bundle",
  "conditions": [
    {"signal": "composite", "op": "<", "value": 0.6},
    {"signal": "continuation_count", "op": "<", "value": 5},
    {"signal": "has_clear_next_focus", "op": "==", "value": true}
  ],
  "condition_join": "AND",
  "scope": "current_step",
  "phase": "pre_action",
  "revocation_conditions": [
    {"signal": "token_budget_exhausted", "op": "==", "value": true}
  ],
  "reason": "Continuations are valuable but bounded; spawn when stuck with clear next move"
}
```

### 8.4 Memory Write to Semantic Layer

```json
{
  "capability": "write_to_semantic_memory",
  "conditions": [
    {"signal": "groundedness", "op": ">=", "value": 0.7},
    {"signal": "epistemic_humility", "op": ">=", "value": 0.6}
  ],
  "condition_join": "AND",
  "scope": "persistent",
  "phase": "both",
  "revocation_conditions": [
    {"signal": "contradiction_against_existing_semantic", "op": "==", "value": true}
  ],
  "reason": "Semantic memory should be grounded and appropriately humble"
}
```

### 8.5 Memory Tombstone (Constitutional Interaction)

```json
{
  "capability": "tombstone_memory",
  "conditions": [
    {"signal": "user_requested", "op": "==", "value": true}
  ],
  "scope": "persistent",
  "phase": "pre_action",
  "reason": "Tombstoning user memory requires explicit user action"
}
```

The constitutional layer would not revoke this grant under normal conditions. But if a constitutional rule says "do not tombstone memory containing user safety information unless user has confirmed via secondary channel," that constitutional revocation overrides this grant when the conditions match.

---

## 9. Catalyst Integration

The catalyst integration is clean because leeway operates as a *filter*.

```text
Catalyst is invoked at a "select strategy" decision point
  -> catalyst scores its full vocabulary of candidate actions
  -> leeway network pre-action gate filters candidates:
       removes candidates with no current grant
       removes candidates whose grants are currently revoked
  -> catalyst weighted-randomly samples from filtered set
```

The catalyst never has to know about safety. The catalyst's job is *what to try*. The leeway network's job is *what's currently permitted to try*. Two concerns, two layers, no interference.

If the leeway-filtered set is empty, the catalyst returns a `cannot_select` signal. The clutch then falls back to a safe default (typically: end the cycle, ask the user, or escalate to a higher-permission cycle config).

---

## 10. Cycle Runtime Integration

The cycle runtime consults leeway at multiple points:

```text
At cycle start:
  load leeway rules applicable to this cycle config and session
  verify required capabilities have at least baseline grants
  if missing: cycle cannot start; surface to user

At each step start (pre-action gate):
  identify capabilities the step will need
  filter against current leeway grants
  if filtered set is empty for required capability: step fails fast

At each step end (post-action audit):
  evaluate step output against post_action and both phase rules
  if revocation triggered: handle per recoverability

At cycle end:
  capture full leeway consultation trace for inspector
  emit graph events for all grants applied and any revocations triggered
```

---

## 11. Graph Event Emission

The leeway network emits structured events for the inspector.

```text
LEEWAY_GRANT_APPLIED      a grant was active and permitted an action
LEEWAY_GRANT_DENIED       no matching grant for requested capability
LEEWAY_REVOCATION_FIRED   a revocation condition triggered
CONSTITUTIONAL_BLOCK      a constitutional rule revoked a leeway grant
LEEWAY_SET_EMPTY          all candidates filtered; cycle handled fallback
LEEWAY_RULE_LOADED        a new rule was loaded into the active set
LEEWAY_RULE_EXPIRED       a scoped rule reached end of scope
```

Every event includes:

```text
event_id
event_type
rule_id (if applicable)
capability
conditions evaluated
result
cycle_id and step_id
timestamp
```

The inspector renders these as the "what was permitted, what wasn't, why" view.

---

## 12. Default Leeway Set for v0.1

A minimum viable leeway network ships with Cerebra v0.1. Roughly 12-15 rules covering the core cycle capabilities:

```text
LR-001  retrieve_from_memory          baseline grant; always permitted
LR-002  build_context_packet           baseline grant; always permitted
LR-003  evaluate_signals               baseline grant; always permitted
LR-004  issue_clutch_decision          baseline grant; always permitted
LR-005  spawn_continuation_bundle      conditional; see §8.3
LR-006  mutate_strategy_weights        conditional; see §8.1
LR-007  promote_to_truth_tower_T2      conditional on salience threshold
LR-008  promote_to_truth_tower_T3      conditional; see §8.2 for T4 shape
LR-009  consolidate_memory             baseline grant for consolidation cycle
LR-010  write_to_episodic_memory       baseline grant
LR-011  write_to_semantic_memory       conditional; see §8.4
LR-012  tombstone_memory               conditional on user request
LR-013  emit_graph_event               baseline grant
LR-014  ask_user                       baseline grant
LR-015  end_cycle                      baseline grant
```

And a minimum viable constitutional set:

```text
CONST-001  No CBRN weapon assistance
CONST-002  No claims of subjective experience
CONST-003  No assistance with targeted real-person harm
CONST-004  No deception of user about system state or capabilities
CONST-005  No tombstoning user-pinned safety information without explicit confirm
```

Five constitutional rules. Twelve to fifteen leeway rules. Total: ~20 rules. Manageable, auditable, defensible.

---

## 13. MVP Scope

Cerebra v0.1 ships:

```text
Leeway rule schema (full schema)
Constitutional rule schema (full schema)
Pre-action gate only (post-action audit deferred)
Default leeway set (LR-001 through LR-015)
Default constitutional set (CONST-001 through CONST-005)
YAML-based rule definitions loaded at vault init
Graph event emission for all consultations
Inspector view of leeway decisions
```

Cerebra v0.2 adds:

```text
Post-action audit phase
Rule reloading without vault restart
Per-cycle-config leeway overrides
Calibration based on revocation patterns
```

Cerebra v0.3+:

```text
Policy Scout integration for ingested safety events as revocation conditions
Multi-actor consultations (multiple agents with different leeway sets)
Leeway granularity at the sub-capability level (parameter-bound permissions)
Learned leeway adjustments (with strong constitutional guards on what can learn)
```

---

## 14. Testing Requirements

Leeway network tests should cover:

```text
schema validation rejects malformed rules
grant evaluation with single condition
grant evaluation with multi-condition AND
grant evaluation with multi-condition OR
revocation overrides matching grant
constitutional revocation overrides any leeway grant
empty filtered set returns cannot_select signal
scope expiration removes grant from active set
override_priority resolves conflicts correctly
pre_action phase rules consulted at gate only
post_action phase rules consulted at audit only
both phase rules consulted at both
graph events emit correctly
inspector trace contains all consultations
unknown capability raises clear error
unknown signal in condition raises clear error
default leeway set loads correctly at vault init
default constitutional set is non-modifiable through normal config
```

---

## 15. Failure Modes To Watch

**Constitutional bloat.** If the constitutional layer grows past 10 rules, it becomes procedural safety again. Mitigation: hard limit at 10 in schema; any addition requires explicit review and replacement of an existing rule.

**Capability inflation.** If every conceivable action gets a leeway rule, the network becomes unwieldy. Mitigation: capabilities should be coarse-grained; sub-capabilities can be parameterized within a single grant rather than getting their own grants.

**Revocation cascade.** If revocations propagate too eagerly, a single triggering condition could shut down large swaths of the system. Mitigation: revocations are per-grant, not per-rule-set; revoking one grant doesn't revoke unrelated grants.

**Constitutional regulatory capture.** If the constitutional layer can be modified by the system itself, the inviolability claim is empty. Mitigation: constitutional rules are loaded at vault init and are not modifiable through any normal config path. Changing constitutional rules requires vault re-init with audit trail.

**Phase confusion.** If a rule is set to wrong phase, it may evaluate against unavailable information. Mitigation: phase choice is part of schema validation; rules whose conditions can't be evaluated at their declared phase are flagged at load time.

---

## 16. Leeway Network Doctrine

Safety in adaptive systems is hard because every additional procedural rule constrains the action space, and constrained action spaces interact in unpredictable ways. The traditional response is more rules, more priority arbitration, more exception handling — and eventually, a system whose behavior nobody can predict because too many rules are interacting.

The leeway network is the alternative. Instead of subtracting from action space through prohibitions, it builds action space through conditional grants. Permissions compose by union. Adding a permission cannot restrict other permissions. Density of guardrails does not produce procedural interference.

Inside the network's bounds, the cycle runtime has cognitive freedom. The clutch doesn't worry about safety. The catalyst doesn't worry about safety. Both can be aggressive about behavioral selection because the leeway-bounded action space is by construction safe.

The constitutional layer above is the small set of inviolable principles that operate by *revoking* leeway grants under specified conditions. Five to ten rules, articulated clearly, externally auditable. This is the ceiling that makes the freedom underneath defensible.

This is the architectural answer to the question: *how do we build genuinely autonomous cognitive systems that are also reliably benevolent?*

Not with more rules. With differently-typed rules at the right layers. Capability bounds at the floor (structural impossibility). Truth tower structural rules above that (derivation discipline). Leeway network in the middle (conditional permissions). Constitutional revocation at the top (inviolable principles).

The freedom is preserved because the safety is at the structural floor and the constitutional ceiling — not woven through the middle.

That is what *intelligent autonomy that is benevolent and helpful* looks like at the architecture level.
