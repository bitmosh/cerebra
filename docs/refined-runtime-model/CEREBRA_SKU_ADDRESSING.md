# Cerebra — SKU Addressing

## 1. Purpose

The SKU is Cerebra's primary memory addressing primitive.

Every memory record receives one or more SKU addresses at write time. SKU addresses are how the runtime locates, navigates, and reasons about memory — before any vector similarity or graph expansion is consulted.

The SKU is not a category code. It is a multi-pointer semantic address with cognitive shape, orthogonal pairing, and relationship type encoded in the digit positions. It replaces "scan and rank" retrieval with "navigate to neighborhood, then refine within it."

This document defines the address shape, the classification subsystem that produces SKUs, the retrieval traversal that consumes them, the synthesis-at-endpoint discipline that fills gaps at sparse addresses, and the self-improving retrieval loop that tunes the system over time.

---

## 2. Core Doctrine

SKU addressing should be:

```text
cognitive-shape-typed
multi-pointer-capable
classification-explainable
calibration-auditable
synthesis-aware
provenance-preserving
self-improving
vector-complementary
```

The SKU's value is in the *navigation graph* the address scheme implies, not the precision of the address.

---

## 3. Address Shape

Every SKU is 10 hex digits, organized as 6 + 2 + 2:

```text
[D1][D2][D3][D4][D5][D6].[D7][D8].[D9][D10]
 \________ location ________/  \entry/ \tag/
```

**Location digits (D1–D6)** encode the cognitive position of the memory:

```text
D1  primary cognitive category (16 options, see §4)
D2  highest-weighted subcategory of D1's primary topic
D3  highest-weighted subcategory of the second-ranked primary
D4  relationship axis between D2 and D3 (16 options, see §6)
D5  temporal band: hour / day / week / month / quarter / archive / timeless / unknown
D6  novelty band: redundant / confirming / extending / surprising / contradicting / pioneering / null
```

**Entry index (D7–D8)** is the per-location occupancy counter:

```text
D7-D8  256 entries per unique location address
```

When a location saturates, that's signal: this address is genuinely active and is a candidate for either deeper subdivision via the type-tag axes or for a consolidation pass.

**Type tag (D9–D10)** encodes orthogonal metadata axes:

```text
D9   modality: text / code / graph / conversation / observation / decision / synthesis / unknown
D10  provenance: observed / consolidated / synthesized / user-pin / external / system / unknown
```

The provenance digit is non-negotiable. Synthesized entries must be distinguishable from observed entries at the address level. Without this, the substrate is contaminated and the system loses the ability to distinguish what it knows from what it concluded.

---

## 4. The 16 Cognitive Categories (D1)

Categories are organized in four quadrants of four. The quadrant structure shows up in the high bits — `0x0-3` is Empirical, `0x4-7` is Generative, `0x8-B` is Normative, `0xC-F` is Relational. This enables quadrant-level filtering with a 2-bit mask before full SKU comparison.

```text
Quadrant I — Empirical / Sense-Making (how things are)
  0x0  OBSERVATION   direct sensory or measurement data; raw events
  0x1  PATTERN       recurrence, regularity, structure across observations
  0x2  MECHANISM     how something works; causal chains; process understanding
  0x3  PHENOMENON    bounded "what it is" knowledge; named things; entities

Quadrant II — Generative / Making (how things come to be)
  0x4  TECHNIQUE     procedural knowledge; how-to; methods; craft
  0x5  DESIGN        intentional structure; choices made for purposes
  0x6  CREATION      works produced; artifacts; outputs; expressions
  0x7  TOOL          instruments and capabilities used to make or do

Quadrant III — Normative / Valuing (how things should be)
  0x8  PRINCIPLE     rules, doctrines, ethics; "should" statements
  0x9  JUDGMENT      evaluations, critiques, appraisals; weighing
  0xA  GOAL          desired states; intentions; what's being pursued
  0xB  CONSTRAINT    limits, prohibitions, what must not be

Quadrant IV — Relational / Connecting (how things relate)
  0xC  EVENT         things that happened in time; moments; situated occurrences
  0xD  AGENT         persons, organizations, systems with intent
  0xE  CONTEXT       settings, environments, scopes
  0xF  RELATION      connections between things; influences, dependencies
```

These are cognitive shapes, not content categories. A memory about evolutionary biology research decomposes as `OBSERVATION × MECHANISM × PRINCIPLE` — three primary candidates with distinct retrieval value. The taxonomy doesn't collapse under abstraction, doesn't overlap viciously, and doesn't reflect a specific worldview. It survives 20 years because shapes of thinking are stable across centuries and cultures.

No miscellaneous bucket. Any memory that resists categorization lands on its closest top three by classifier score.

---

## 5. Subcategory Layout (D2 and D3)

Each top-level category has its own 16 subcategories. D2 selects from the primary category's subcategory set; D3 selects from the second-ranked primary's subcategory set.

Initial subcategory layouts are defined in `CEREBRA_SKU_SUBCATEGORIES.md` (separate doc, ~256 entries total). For MVP, only the most-used subcategory sets need to be enumerated. Unused subcategory slots are reserved for later refinement.

The subcategory layouts are versioned. Changes require schema migration and SKU rewrite. They should be stable.

---

## 6. Relationship Axis (D4)

D4 encodes how D2 relates to D3. Sixteen relationship types, organized in four families:

```text
Comparative:
  0x0  analogy        D2 is structurally similar to D3
  0x1  contrast       D2 differs sharply from D3 in instructive ways
  0x2  unification    D2 and D3 are revealed as the same underlying thing
  0x3  tension        D2 and D3 are in productive conflict

Causal:
  0x4  enables        D2 makes D3 possible or easier
  0x5  prevents       D2 blocks or constrains D3
  0x6  emerges-from   D3 arises as a consequence of D2
  0x7  transforms     D2 changes D3 in a specific way

Compositional:
  0x8  contains       D2 has D3 as part of itself
  0x9  part-of        D2 is a piece of D3
  0xA  composes       D2 and D3 together form a larger whole
  0xB  decomposes     D2 breaks down into D3 (among others)

Operational:
  0xC  applies-to     D2 is used on or against D3
  0xD  critiques      D2 evaluates or challenges D3
  0xE  serves         D2 exists in service of D3
  0xF  derives-from   D2 is calculated, learned, or extracted from D3
```

The constrained vocabulary is the move that unlocks D4. The classifier prompt becomes: "given D2 and D3, which of these 16 relationships best describes how they connect?" High classification reliability vs open-ended category assignment.

Relationship queries become tractable: "find memories where MECHANISM enables PRINCIPLE" is a one-digit query at D4.

---

## 7. Multi-Pointer Fanout

A single memory accumulates multiple SKU addresses based on how its content distributes across categories.

**Fanout rules:**

```text
Category candidates with classifier score ≥ 0.4 are eligible.
Top 3 candidates become D1/D2/D3 anchors of the primary SKU.
Additional candidates with score ≥ 0.6 become sibling pointer SKUs.
Hard cap: 12 SKU addresses per memory.
Any memory using more than 4 SKUs requires a fanout justification field.
```

The justification field keeps the system honest. If every memory wants 12 pointers, the discrimination benefit is lost. The justification documents what specific cross-references each pointer enables.

**Single-focus fallback:** if only one category clears 0.4, the memory is unusually focused. D2 and D3 fall back to subcategory-of-primary at two levels of refinement (classic hierarchy for this edge case).

**Empty-position handling:** unused positions encode as `null` (a reserved hex value), not as zero. Null positions are informative — they say "this memory has no meaningful value at this axis."

---

## 8. Classification Subsystem

The SKU classifier is its own subsystem with its own prompt + formula pairing, separate from the cycle's signal evaluation. It operates on raw memory content, not on cognitive performance.

**Classifier shape:**

```text
input: memory content + optional context hints
prompt: rates content's fit on all 16 categories on a 0-1 scale
formula: confidence-weighted ranking with explicit thresholds
output: SKU addresses + classifier confidence + alternative candidates
```

**Confidence thresholds:**

```text
≥ 0.6   strong; eligible for sibling pointer
≥ 0.4   eligible for D1/D2/D3 anchor positions
< 0.4   discarded (does not enter SKU)
```

**Multi-prompt triangulation:** for high-stakes memories (high salience, user-pinned, or being promoted by consolidation), run 3 classifier passes with slightly different prompts and triangulate. Agreement increases confidence; divergence flags the memory for review.

**Calibration audit hook:** the consolidation engine periodically samples classified memories and compares classifier output to outcomes — were memories retrieved via D1 actually about D1's content? Calibration deltas update the classifier's per-category weight adjustments. This is the prediction-error layer feeding back into the classifier itself.

---

## 9. Synthesis at Endpoint

When retrieval lands at a SKU address and the data there is sparse or contextually incomplete, the cycle runtime may invoke synthesis: pull adjacent addresses through sibling pointers, generate the inferred missing context, write it back at that address.

**Non-negotiable disciplines:**

```text
1. Provenance digit (D10) must mark synthesis as synthesized, not observed.
2. Synthesis must be idempotent-aware: asking the system to fill the
   same gap twice strengthens the first synthesis or flags a conflict,
   not produces two parallel synthetic entries.
3. Synthesis routes through the consolidation engine's dedup machinery,
   not as a separate write path.
4. Synthetic entries have lower default salience than observed entries
   in the same address (unless cross-validated by multiple synthesis passes).
```

Without these disciplines, synthetic entries contaminate the substrate and the system loses the ability to distinguish what it knows from what it concluded. This is the discipline that turns Cerebra from "storage with smart retrieval" into "active reasoning substrate" without losing epistemic integrity.

---

## 10. Pointer Staleness

When consolidation rewrites memory (summary produced at address Y compresses entries from address X), SKU pointers must remain valid.

**Policy: chain-of-redirects with max-chain-length 3.**

```text
X tombstoned with forwarding pointer to Y
Y tombstoned with forwarding pointer to Z
Z tombstoned with forwarding pointer to W
W is end-of-chain; pointer to X resolves directly to W with notice
```

Beyond chain length 3, force rewrite of original pointers. This composes with Cerebra's existing tombstone discipline without inventing new mechanisms.

---

## 11. Retrieval Traversal

SKU retrieval is attention-budgeted. The cycle runtime's clutch can set the retrieval depth based on query complexity and budget pressure.

**Step 1 — Query SKU construction.**

```text
The agent parses the incoming query and constructs a partial SKU pattern.
D1 confidently if primary category is clear.
D2/D3 with confidence weights.
D4 only if relationship type is explicit in query.
D5-D10 only if query specifies them ("from last week" sets D5; "code only" sets D9).
```

**Step 2 — Exact match.**

```text
Memories whose SKU matches the query SKU exactly (or matches all non-null
query digits exactly) come back instantly.
If this returns enough high-quality results, stop here.
```

**Step 3 — Partial match with priority.**

```text
Match D1, D2, D3 (semantic core) but allow D4-D10 to vary.
Catches memories about the right thing in different temporal/modality bands.
```

**Step 4 — Sibling pointer traversal.**

```text
Take best candidates from step 3 and follow their other SKU pointers.
Walk the semantic neighborhood through multi-pointer fanout.
This is where SKU outperforms vector search: navigation through interpretable
neighbors, not just similarity neighbors.
```

**Step 5 — Bounded vector fallback.**

```text
If insufficient candidates after steps 1-4, fall back to vector similarity
on the union of (candidates collected so far + 1-hop sibling expansion).
Cap at 200 candidates total to keep vector cost bounded.
Vector ranker never scans the entire vault.
```

**Step 6 — Interpretation surface.**

```text
Every retrieved memory carries a retrieval path annotation:
  "exact match on D1+D2"
  "sibling pointer from 0x3A7F.B2.04"
  "vector fallback within partial-match neighborhood"
This is the differentiator vs pure RAG: retrieval is explainable.
```

---

## 12. Self-Improving Retrieval

Retrieval strategies are bandit arms.

**The strategy space:**

```text
shallow_exact         stops at step 2
shallow_partial       stops at step 3
medium_sibling        stops at step 4 with conservative expansion
medium_sibling_wide   stops at step 4 with aggressive expansion
deep_vector_bounded   runs full step 5 with 100-candidate cap
deep_vector_full      runs full step 5 with 200-candidate cap
adaptive              picks strategy based on query SKU shape
```

**The learning loop:**

```text
each retrieval produces (strategy_used, query_shape, candidates_returned,
                          user_or_agent_engagement_signal)
the bandit primitive (from lattica-primitives) updates strategy stats
per query-shape
over time, the system learns which strategy works for which query type
```

**The pitch property:** Cerebra isn't just a memory architecture. It's a memory architecture with built-in self-improvement on the retrieval side. The system gets better at retrieving over time, not just better at storing.

This is the part of Cerebra that no published memory system has. Vector-only retrieval is a fixed function; SKU + bandit-driven strategy selection is a learned function. The improvement compounds with use.

---

## 13. Integration With Existing Cerebra Components

**Retrieval Architecture (`CEREBRA_RETRIEVAL_ARCHITECTURE.md`):** all retrieval modes (lexical, vector, metadata, graph-expansion) operate over the SKU-addressed substrate. SKU is not a fifth retrieval mode — it is the precondition for the other four to be efficient.

**Memory Layers (`CEREBRA_MEMORY_LAYERS.md`):** every memory record at M2 and above carries a SKU. Layer-specific subcategory sets may vary; the addressing scheme is uniform.

**Consolidation Engine (`CEREBRA_CONSOLIDATION_ENGINE.md`):** consolidation rewrites SKU pointers when summaries are produced. Consolidation also runs calibration audits on the classifier. Consolidation triggers the ablation primitive (see `CEREBRA_ORTHOGONAL_ABLATION.md`).

**Salience Scoring (`CEREBRA_SALIENCE_SCORING.md`):** SKU-sibling-distance is a new salience component (closer in SKU space = higher salience for related queries). Attribution-aligned-match is a new salience component (match position aligned with high-attribution position = higher salience).

**Cycle Runtime (`CEREBRA_COGNITIVE_RUNTIME.md`):** the clutch's retrieval-depth action chooses how many SKU steps to traverse. The catalyst's strategy-selection includes retrieval strategies as bandit arms.

**Truth Tower (forthcoming `CEREBRA_TRUTH_TOWER.md`):** the tower's tier-derivation operations reach into memory via SKU addresses, not raw queries. Cross-references between tower tiers are SKU-pointer-shaped.

---

## 14. MVP Scope

Cerebra v0.1 should implement:

```text
SKU computation at write time (D1-D4 anchor digits + D9-D10 type tags)
Single-pointer SKU storage (fanout to v0.2)
Exact-match retrieval (step 1-2 of traversal)
Sibling-pointer traversal (step 4) for explicit follow-the-pointer queries
Vector fallback (step 5) using existing vector index
Classifier subsystem with single-pass prompt
Provenance digit enforcement (synthesized vs observed)
Pointer staleness via chain-of-redirects (max chain 3)
Retrieval path annotation in all results
```

Deferred to v0.2:

```text
Multi-pointer fanout with sibling pointers
Multi-prompt triangulation for high-stakes classification
Calibration audit hook
Self-improving retrieval via bandit
Synthesis at endpoint
Subcategory schemas beyond the most-used 4-5 categories
```

Deferred to v0.3+:

```text
Dream/retrain integration (full SKU + attribution metadata as training signal)
Cross-vault SKU federation
```

---

## 15. Testing Requirements

SKU tests should cover:

```text
classifier produces stable SKUs for unchanged content
classifier produces different SKUs for content with shifted primary
high-confidence classifications agree across triangulated prompts
synthesis writes are tagged as synthesized in D10
re-synthesis of same gap strengthens existing entry (idempotency)
chain-of-redirects resolves through 3 hops
chain-of-redirects forces rewrite at length > 3
exact-match retrieval returns expected memories
partial-match retrieval expands appropriately
sibling traversal follows pointers correctly
vector fallback respects 200-candidate cap
retrieval path annotation present on every result
quadrant-level filtering via 2-bit mask works
empty-position null handling
```

---

## 16. SKU Doctrine

The SKU's value is not in the precision of any single address. It is in the navigation graph the address scheme implies.

Vector-only memory systems treat memory as a database problem. SKU treats memory as a cognitive problem. The categories aren't labels — they are cognitive shapes. The relationships aren't tags — they are the structure of how shapes connect.

A memory system that knows what kind of cognitive object each memory is can do moves no flat-embedding system can do:

```text
explain why a memory was retrieved
prefilter the candidate set before vector cost is paid
navigate from query-shape to memory-region instead of scanning
distinguish what it knows from what it concluded
attribute value to the right aspects of a memory
learn which retrieval strategies work for which queries
```

This is the substrate that makes the rest of Cerebra possible. Get this right and the truth tower, the leeway network, the orthogonal ablation, and the eventual dream/retrain direction all compose on top of it cleanly.

Get this wrong and everything above it inherits the error.
