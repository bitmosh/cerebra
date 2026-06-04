# Cerebra — Truth Tower

## 1. Purpose

The truth tower is Cerebra's structured cognitive workspace.

Working memory holds a flat set of attention items — high-salience memories sitting in slots, available to the agent. The truth tower is the *derived structure built on top of working memory*: a stratified stack of cross-referenced insights, with raw evidence at the base and the system's current best understanding at the top.

The truth tower exists because flat working memory is insufficient for sustained cognitive work. A flat attention set can hold what matters; it cannot represent how what matters *fits together*. The tower's tiers, capacity caps, and cross-reference requirements turn working memory from "items in mind" into "structured understanding in mind."

This document defines the tier structure, the derivation operations between tiers, the staleness propagation rules, the render formats that project the tower into prompts, and the integration with the cycle runtime and SKU addressing.

---

## 2. Core Doctrine

The truth tower should be:

```text
tier-structured
cross-referenced
derived-bottom-up
staleness-aware
multi-render-capable
budget-bounded
inspectable
sku-addressed
```

The tower's value is structural. Rules attach to tiers, not to content. This is what lets the system have dense cognitive discipline without procedural rules interfering with each other.

---

## 3. Tier Structure

Five tiers, capacity-capped at each level. Capacity decreases as you ascend because higher tiers represent more distilled understanding.

```text
T5  Active Goal              capacity: 1
T4  Working Hypotheses       capacity: 2-4
T3  Cross-Validated Insights capacity: 3-7
T2  High-Salience Memories   capacity: 5-12
T1  Source-Grounded Evidence capacity: 10-20
```

Each tier has:

```text
capacity_cap          maximum items the tier can hold
salience_aggregation  how the tier scores items
cross_ref_requirement minimum lower-tier citations per item
re_derivation_hook    when lower tiers change, what marks stale
```

---

## 4. T1 — Source-Grounded Evidence

The tower's foundation. Raw retrieval candidates from the memory layer.

```text
capacity: 10-20 items
sources: M2 chunks, M3 episodic events, M5 semantic memories
cross_ref: none required (this is the bottom)
items carry: SKU address + provenance chain + retrieval path annotation
```

T1 is populated by the retrieval engine after each query or context-shift event. It represents *what the system has access to* relative to the current cycle's focus.

---

## 5. T2 — High-Salience Memories

Items from working memory that have cleared the salience threshold for tower inclusion.

```text
capacity: 5-12 items
sources: M4 working memory, filtered by salience score
cross_ref: each T2 item must cite ≥ 1 T1 evidence item (or be user-pinned)
items carry: SKU address + salience components + reason_in_tower
```

T2 is where working memory items become *structured in the tower*. The act of citing T1 evidence converts a raw memory into an item with a position in the tower's logic.

---

## 6. T3 — Cross-Validated Insights

The first tier that contains *derived* content rather than retrieved content. T3 items are insights that have been validated by triangulation across multiple T2 items.

```text
capacity: 3-7 items
sources: derived by the cycle runtime from T2 cross-references
cross_ref: each T3 item must cite ≥ 2 T2 items
items carry: SKU address + derivation provenance + confidence
```

A T3 item is only as trustworthy as its supporting T2 items. If the supports contradict each other, the T3 insight should reflect the contradiction explicitly, not silently resolve it.

---

## 7. T4 — Working Hypotheses

Active hypotheses the cycle is exploring or testing.

```text
capacity: 2-4 items
sources: derived from T3, or from explicit cycle goals
cross_ref: each T4 item must cite ≥ 1 T3 insight or 2 T2 items
items carry: SKU address + supporting_insights + counter_evidence
```

T4 is contested space. Multiple hypotheses can coexist; the cycle runtime is actively weighing them. T4 items carry counter-evidence pointers, not just supporting evidence. This is where the tower represents *what the system isn't yet sure about*.

---

## 8. T5 — Active Goal

The cycle's anchor.

```text
capacity: 1 (exactly one)
sources: user intent or cycle config
cross_ref: cites whatever T4 hypotheses currently serve the goal
items carry: goal_statement + success_criteria + constraints
```

The goal at T5 is the only item in the tower that does not derive from lower tiers. It sets direction; everything below it serves it. If T5 changes, the entire tower below is re-evaluated for relevance to the new goal.

---

## 9. Derivation Operations

The tower is built bottom-up by a small set of operations. The cycle runtime invokes these; the clutch decides when.

```text
PROMOTE(item, target_tier)
  Propose an item to a higher tier.
  Validates cross-reference requirement.
  Validates capacity (may trigger eviction at target tier).

LINK(higher_item, lower_items[])
  Declare cross-references between tiers.
  Updates derivation provenance.
  Strengthens higher_item's confidence.

STALE(item)
  Mark an item as stale because supporting items changed.
  Does not remove the item; flags for re-derivation.

REBUILD(tier)
  Re-derive a tier from current lower tiers.
  Used when staleness accumulates.

COLLAPSE(tier)
  Discard a tier entirely and rebuild from below.
  Used when the cycle's frame shifts substantially.

EVICT(item)
  Remove an item from its tier.
  Triggered by capacity pressure or explicit cycle decision.
```

These are the only ways the tower changes. Items don't move silently; every change emits an event for the inspector.

---

## 10. Staleness Propagation

When a T1 evidence item is evicted or its lifecycle state changes (e.g., tombstoned), every higher-tier item that cited it gets marked stale.

```text
T1 item evicted -> all T2 items citing it: STALE
T2 item stale   -> all T3 items citing it: STALE (transitively)
T3 item stale   -> all T4 items citing it: STALE (transitively)
T4 item stale   -> T5 goal: NOT marked stale (goal is anchored externally)
                  but T5's hypothesis-support set is recomputed
```

Stale items remain visible (the cycle may still find value in them) but cannot be cited by *new* derivations. The next REBUILD operation purges or re-derives stale items.

This is the discipline that prevents the tower from becoming a house of cards. When evidence shifts, the consequences propagate visibly.

---

## 11. Capacity and Contention

Capacity caps create contention. New items entering a saturated tier must displace existing items.

**Eviction policy:** lowest-salience item wins eviction in most cases. Exceptions:

```text
user-pinned items are non-evictable
items currently cited by higher tiers are eviction-resistant
   (penalty applied to newcomer's salience comparison)
items in the last N cycles that produced good outcomes get recency boost
```

**Tier-promotion thresholds:**

```text
T1 -> T2: salience ≥ 0.5 AND cited by ≥ 1 T2 attempt OR user_pin
T2 -> T3: requires explicit derivation step (DERIVE_INSIGHT operation)
T3 -> T4: requires explicit hypothesis formation (FORM_HYPOTHESIS operation)
T4 -> T5: not possible — T5 is set externally
```

The asymmetry is intentional. Lower tiers populate automatically from retrieval and working memory; higher tiers require *deliberate cognitive work* to populate. The tower's structure embeds the discipline that understanding is built, not retrieved.

---

## 12. Render Formats

The same tower content can render into prompts in multiple formats. The truth tower stays canonical; the renderer picks the format that fits the current cycle's needs.

**Chronological:**

```text
T1 evidence first (chronologically ordered)
T2 memories interleaved with evidence they cite
T3 insights as commentary on the evidence stream
T4 hypotheses as "currently considering..."
T5 goal at the top as anchor
```

Best for "show me how you got here" prompts and audit views.

**Top-down:**

```text
T5 goal at the top
T4 hypotheses with their counter-evidence
T3 insights as supporting structure
T1+T2 collapsed to citations
```

Best for "act on current best understanding" prompts.

**Cross-validation:**

```text
T3 insights as primary content
each T3 item shown with its T2 supports inline
T1 evidence as cite-only references
T4 hypotheses shown as "if T3 holds, then..."
T5 goal at the top as scope
```

Best for "what do you actually know" prompts and confidence audits.

**Adversarial:**

```text
T3 contradicting insights rendered side-by-side
T4 hypotheses with explicit counter-hypotheses
goal: ask agent to reconcile
T1/T2 supports inline for each side
```

Best for critique cycles, debugging, decision analysis.

**Topical (SKU-grouped):**

```text
Items grouped by SKU quadrant
each group internally tier-ordered
useful when query spans multiple cognitive shapes
```

Best for "what about X" prompts where X has unclear cognitive shape.

---

## 13. Token Budget Discipline

The tower has structure; rendering has budget.

```text
budget_total = ContextPacket.max_tokens - task_overhead

budget_distribution (default):
  T5 goal:           5%
  T4 hypotheses:     15%
  T3 insights:       25%
  T2 memories:       30%
  T1 evidence:       25%
```

Adjustable per render format. Adversarial mode allocates more to T3+T4; chronological mode allocates more to T1.

If total exceeds budget, items are dropped from the bottom of each tier (lowest-salience first) until budget fits. The drop is logged; the inspector can show "what was in the tower but didn't make this render."

---

## 14. Integration With SKU and Working Memory

**SKU addressing (`CEREBRA_SKU_ADDRESSING.md`):** every tower item carries its SKU. Cross-references between tiers are SKU-pointer-shaped, not raw object references. This means the tower survives tier rebuilds correctly — the pointer resolves through any consolidation that happened to underlying memories.

**Working Memory (`CEREBRA_WORKING_MEMORY_AND_ATTENTION.md`):** the tower is *not* working memory. Working memory's M4 slots hold raw attention items; the tower is M4.5, a derived structure built from them. Working memory says what's in mind; the tower says how what's in mind fits together.

**Cycle Runtime (`CEREBRA_COGNITIVE_RUNTIME.md`):** the cycle's clutch can issue tower-shaping actions:

```text
BUILD_TOWER       derive T3/T4 from current T1/T2
REBUILD_TIER(t)   refresh a stale tier
COLLAPSE_TIER(t)  discard a tier and rebuild from below
PROMOTE(item, t)  explicitly promote an item to higher tier
```

These are new clutch actions in the structural group (per the action grouping discussed in cognitive runtime).

**Re-injection Loop (forthcoming `CEREBRA_REINJECTION_LOOP.md`):** ContinuationBundles draw from tower projections, not raw working memory. The tower is what carries forward; working memory rebuilds in the new cycle from the carry-forward.

---

## 15. MVP Scope

Cerebra v0.1 should implement:

```text
T1 + T2 only (T3, T4, T5 deferred to v0.2)
Manual PROMOTE operation (no auto-derivation)
Simple capacity caps (T1=10, T2=5)
One render format: chronological
SKU-based cross-references
Tower events emitted for inspector
No staleness propagation in v0.1 (full rebuild on each tower interaction)
```

Cerebra v0.2 adds:

```text
T3 (cross-validated insights) with DERIVE_INSIGHT operation
Staleness propagation
Multi-render formats (top-down, cross-validation)
Capacity contention with eviction policy
Budget-aware rendering
```

Cerebra v0.3+:

```text
T4 (working hypotheses) with FORM_HYPOTHESIS operation
T5 (active goal) as anchor with full re-evaluation on goal change
Adversarial render format
Topical SKU-grouped render
Tower-snapshot persistence and replay
```

---

## 16. Testing Requirements

Truth tower tests should cover:

```text
T1 populates from retrieval results
T2 promotion respects salience threshold
T2 items must cite T1 (cross-ref validation)
capacity caps enforce eviction
user-pinned items are non-evictable
items cited by higher tiers resist eviction
staleness propagates through tiers correctly
T5 goal is non-derivable from lower tiers
render formats produce different layouts from same tower
budget discipline drops lowest-salience first
SKU cross-references survive consolidation
tower events emit correctly
REBUILD operation purges stale items
```

---

## 17. Truth Tower Doctrine

A flat attention set is sufficient for retrieval. A structured cognitive workspace is required for understanding.

The truth tower is the architectural primitive that makes the difference visible. Items don't just sit in attention — they cite each other, support each other, contest each other, and serve a goal. The structure embeds the discipline that real cognition has layers, that conclusions rest on evidence, that hypotheses are tested against alternatives, that goals anchor activity.

When the system renders its truth tower to a user, the user sees not just *what the system thinks* but *why it thinks that, what it's still unsure about, and what it's working toward*. That is the inspection property that distinguishes a memory system that thinks from a memory system that retrieves.

The tower is small in code (the tiers are bounded, the operations are few), large in implication (it is the difference between flat retrieval and structured cognition), and disciplined in cost (capacity caps prevent runaway, budget rendering prevents context bloat).

Build it carefully. Everything above retrieval depends on it.
