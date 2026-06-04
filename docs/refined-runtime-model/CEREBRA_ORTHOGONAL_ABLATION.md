# Cerebra — Orthogonal Ablation

## 1. Purpose

Orthogonal ablation is the analytical primitive that lets Cerebra attribute value to the right aspects of a memory.

When the SKU classifier places a memory at `D2 × D3` (an orthogonal pair under relationship D4), the system knows the pair was useful enough to anchor the address. It does not know which side carried the weight. Was D2 the load-bearing aspect and D3 contextual support? Was D3 the insight and D2 the evidence? Did the pair produce emergent value that neither side carries alone?

Orthogonal ablation answers that question by splitting the pair, evaluating each element in alternative orthogonal contexts, and reattributing value to the elements and their combination.

This document defines the SOLO, RECOMBINE, and CHALLENGE operations, the ContributionProfile schema they produce, the scheduling discipline that keeps cost bounded, and the feedback loops that consume attribution data to improve the system over time.

---

## 2. Core Doctrine

Orthogonal ablation should be:

```text
attribution-explicit
classifier-calibrating
retrieval-improving
budget-disciplined
confidence-aware
dream-retrain-ready
non-magical
```

Ablation is not a truth detector. It is calibrated self-report that tells the system which aspects of a memory carry value within the current classification scheme. If the scheme is biased, ablation reproduces the bias. Acting on low-confidence ablation data is worse than acting on no ablation data.

---

## 3. What Ablation Unlocks

**Causal attribution in memory.** Every SKU position carries positional credit. Ablation adds attributional credit: "this memory's value is 73% from its MECHANISM aspect, 22% from OBSERVATION, 5% emergent from their specific pairing."

**Classifier calibration signal.** When ablation shows the classifier was wrong about which digit was primary, that's a calibration error. The classifier learns its own systematic biases over time.

**Sibling pointer pruning.** Pointers whose element scores well alone justify their existence. Pointers whose element only matters in combination justify existence as the combinatorial case. Pointers that score badly in both modes are classification noise — prune them.

**Stronger retrieval interpretability.** "This memory was retrieved because its MECHANISM aspect matched your query — note that MECHANISM is 73% of this memory's value, so the match is high-confidence" is a different kind of explanation than current systems can produce.

**Dream/retrain training signal.** Standard dream/retrain produces a pattern-matcher. Dream/retrain on memories with ContributionProfiles attached produces a model that has learned which aspects of each memory carry which kinds of value — the substrate of understanding rather than recombination.

---

## 4. The Three Operations

### 4.1 SOLO

Take element X from an orthogonal pair `X × Y`. Recompose X with K different other orthogonal partners drawn from memories where X scores well. Run the classifier on those recompositions and ask: how does X's contribution score change across the new pairings?

```text
ablate_solo(memory, element_position) -> SoloProfile {
  element: X
  original_partner: Y
  test_partners: [Z1, Z2, ..., Zk]    # k typically 3-5
  scores_across_partners: [s1, s2, ..., sk]
  mean_solo_value: float              # X's average contribution regardless of partner
  variance: float                     # how much partner choice matters for X
  interpretation:
    high mean, low variance   -> X is independently valuable
    high mean, high variance  -> X is contextually valuable
    low mean, any variance    -> X was not the load-bearing element in original
}
```

### 4.2 RECOMBINE

Take both elements X and Y from the original pair. Recombine them under different relationship axes (different D4 values). Does `X × Y under "enables"` score similarly to `X × Y under "contrasts"`? If yes, the relationship was incidental. If no, the relationship type carries real value.

```text
ablate_recombine(memory) -> RecombineProfile {
  pair: (X, Y)
  original_relationship: R
  test_relationships: [R1, R2, ..., Rm]   # 4-8 plausible alternatives from the 16
  scores: [s1, s2, ..., sm]
  original_relationship_advantage: float  # how much better R scored than alternatives
}
```

### 4.3 CHALLENGE

Take an element and place it against deliberately non-matching partners — partners drawn from a different quadrant or with weak topical fit. This is the negative control. If X still produces some value against random partners, X has standalone value. If X collapses to zero with bad partners, X was entirely partner-dependent.

```text
ablate_challenge(memory, element_position) -> ChallengeProfile {
  element: X
  weak_partners: [W1, W2, ..., Wn]    # n typically 3-5
  scores: [s1, s2, ..., sn]
  floor_value: float                  # X's minimum value when poorly paired
  standalone_strength: float          # floor_value normalized against original score
}
```

---

## 5. ContributionProfile

The three operations together produce a contribution profile that gets stored as metadata on the original memory.

```json
{
  "memory_id": "mem_abc123",
  "sku": "0x2A.D1.3F.04.B2.04",
  "d1_attribution": 0.41,
  "d2_attribution": 0.32,
  "d3_attribution": 0.18,
  "d4_attribution": 0.04,
  "emergent_residual": 0.05,
  "confidence": 0.74,
  "ablation_at": 1717459200,
  "ablation_cost_tokens": 4820,
  "solo_profiles": ["solo_id_1", "solo_id_2"],
  "recombine_profile_id": "rec_id_1",
  "challenge_profiles": ["chal_id_1", "chal_id_2"]
}
```

Attributions sum to 1.0. The `emergent_residual` field captures value that no individual element carries alone — value that exists only in the specific combination.

Confidence under 0.6 means the ablation result is unreliable and downstream consumers should fall back to default behavior.

---

## 6. When Ablation Runs

Ablation is expensive. Multiple recompositions, each requiring classifier passes. Smart placement matters more than aggressive scheduling.

**At consolidation time, for memories being promoted.** When a memory crosses a salience threshold and is being promoted from episodic to semantic, the consolidation engine runs ablation as part of the promotion. The memory is now important enough to justify the cost; the promotion machinery is already running; the attribution metadata is needed for downstream retrieval anyway.

**During dream sessions, sampled.** When the deep-reflection async process exists (post-MVP), it samples memories for ablation analysis with a bias toward memories that have been retrieved often but whose retrieval performance is mixed. High-traffic, uncertain quality — these are the memories where attribution data would change behavior.

**On-demand, for the inspector.** When a user asks "why was this memory retrieved" through the inspector surface, the system can run ablation in real time if attribution data is missing. Most expensive case, happens rarely.

**Never automatically on every write.** Write-time ablation would 5-10x the cost of memory ingestion. Not worth it.

**Budget cap.** Daily ablation budget should be configurable. Default: 100 ablations per day for v0.2, scaling with use. Ablations queue when budget is exhausted and run on the next cycle's quiescent period.

---

## 7. Feedback Loops

Three closed loops, in order of importance.

### 7.1 Classifier Calibration

When ablation shows the classifier was wrong about which digit was primary, that's a calibration error. The calibration audit hook in the consolidation engine gets a new signal type: `positional_attribution_error`.

```text
For each ablated memory:
  if d1_attribution > d2_attribution and classifier ranked d1 first: correct
  if d1_attribution < d2_attribution and classifier ranked d1 first: error
  if d1_attribution << d2_attribution and classifier ranked d1 first: severe error
```

Severe errors accumulate per-category. Over time, per-category calibration weights adjust:

```text
"I tend to over-weight MECHANISM when the actual load-bearing element was OBSERVATION
 -> nudge classifier weight for MECHANISM down by small delta when both fire above threshold."
```

This is prediction-error learning applied to the classifier itself.

### 7.2 Retrieval Ranking

When a query matches a memory via D2 (say, MECHANISM), and that memory's attribution shows D2 is only 12% of its value, the retrieval engine knows this is a weak match.

```text
match_quality = base_match_score × match_position_attribution
```

Boost ranking when match-position aligns with high-attribution position. Suppress when it aligns with low-attribution position.

This is a major retrieval quality improvement and it costs nothing at retrieval time. The attribution work was done at consolidation.

New salience component for `CEREBRA_SALIENCE_SCORING.md`:

```text
attribution_aligned_match: how well the query's match position aligns with
                           the memory's high-attribution positions
```

### 7.3 Catalyst Strategy Refinement

The catalyst chooses which strategies to mutate. With attribution data, the catalyst can see which strategies historically produced memories with high-attribution outcomes vs high-emergent-residual outcomes.

```text
Analytical refinement strategies tend to produce memories whose value is
   clearly attributable to specific aspects.
Combinatorial exploration strategies tend to produce memories with high
   emergent residual — value that lives in the combination.
```

The catalyst learns which strategy to deploy for which kind of value the user is currently seeking. This couples to the cycle's mode: planning cycles tend to want attributable outputs; exploration cycles tend to want emergent outputs.

---

## 8. The Dream/Retrain Connection

When the system eventually does deep reflection sessions and trains a small specialized model on its own memory bank, ablation is the operation that turns those sessions into understanding rather than recombination.

A model trained on "this is a MECHANISM × DESIGN memory" learns surface patterns.

A model trained on "this is a MECHANISM × DESIGN memory where MECHANISM is 73% load-bearing, DESIGN is 22% support, and the rest is emergent from their specific pairing under the 'enables' relationship" learns the shape of valuable cognitive objects.

The second training signal is what produces the real-understanding-not-pseudo property. Without ablation, dream/retrain is fine-tuning. With ablation, dream/retrain teaches the model what it means for something to be worth knowing.

This is post-MVP, but the foundational decisions in SKU and ablation should preserve enough metadata that dream/retrain has hooks to grab onto.

---

## 9. Integration Points

**SKU Addressing (`CEREBRA_SKU_ADDRESSING.md`):** ablation operates over SKU addresses. The classifier subsystem provides the scoring function that ablation invokes. Ablation outputs become metadata adjacent to SKUs.

**Consolidation Engine (`CEREBRA_CONSOLIDATION_ENGINE.md`):** consolidation triggers ablation as part of memory promotion. Calibration audit consumes ablation output.

**Salience Scoring (`CEREBRA_SALIENCE_SCORING.md`):** `attribution_aligned_match` becomes a new salience component.

**Prediction and Evaluation (`CEREBRA_PREDICTION_AND_EVALUATION.md`):** classifier calibration is prediction-error learning at the SKU classification layer. ContributionProfiles feed the prediction layer's training data.

**Cycle Runtime (`CEREBRA_COGNITIVE_RUNTIME.md`):** the catalyst consumes attribution patterns when selecting strategies. The clutch can request ablation as a deliberate action when a memory is being considered for high-stakes use.

**Inspector (forthcoming):** attribution data is rendered to users in retrieval explanations and memory inspection views.

---

## 10. MVP Scope

Orthogonal ablation is **not in Cerebra v0.1**.

v0.1 ships SKU addressing with the classifier producing single-pass classifications. Ablation requires the multi-pass classifier infrastructure plus the consolidation-time scheduling, neither of which is MVP-shaped.

**Cerebra v0.2** introduces ablation as follows:

```text
SOLO operation only (RECOMBINE and CHALLENGE defer to v0.3)
ablation runs only at consolidation promotion
single ContributionProfile per memory
classifier calibration loop active
retrieval ranking uses attribution_aligned_match
catalyst does not yet consume attribution
daily budget cap enforced
```

**Cerebra v0.3+:**

```text
RECOMBINE and CHALLENGE operations
ablation during dream sessions
catalyst-strategy refinement from attribution patterns
inspector renders attribution in real time
dream/retrain integration begins
```

**The forward-compatibility discipline for v0.1:** the SKU classifier in v0.1 must preserve enough metadata about its decision process that v0.2 ablation has hooks to grab onto. Specifically:

```text
classifier output includes per-category scores for all 16 categories
   (not just the top 3 that became digits)
classifier output includes confidence per anchor position
classifier output is stored alongside the SKU, not discarded after digit assignment
```

This costs nothing in v0.1 and saves a major refactor in v0.2.

---

## 11. Testing Requirements

Ablation tests should cover:

```text
SOLO operation produces stable scores across repeated runs
SOLO variance reflects partner sensitivity correctly
RECOMBINE correctly identifies cases where relationship matters
RECOMBINE returns flat scores when relationship is incidental
CHALLENGE returns low floor for partner-dependent elements
CHALLENGE returns reasonable floor for standalone-valuable elements
ContributionProfile attributions sum to 1.0 (with emergent_residual)
confidence below threshold prevents downstream consumption
budget cap enforced
calibration audit consumes ablation output correctly
retrieval ranking applies attribution_aligned_match
classifier metadata preservation works in v0.1 for v0.2 compatibility
```

---

## 12. Failure Modes To Watch

**Bias amplification.** If the classifier is biased and ablation calibrates against the classifier's own outputs, the system can converge on its own biases as if they were truth. Mitigation: periodic human review of calibration deltas. If the classifier's bias adjustments trend strongly in one direction over time, flag for review.

**Confidence inflation.** Ablation produces a confidence score. If that score is itself biased, downstream consumers will trust unreliable attributions. Mitigation: validate ablation confidence against retrieval outcomes — high-confidence ablations whose attribution doesn't predict retrieval success indicate confidence inflation.

**Cost runaway.** Each ablation is multiple classifier passes. If consolidation runs ablation on every promoted memory and promotions are frequent, cost can spike. Mitigation: hard budget cap, queue overflow handling, periodic cost audit.

**Combinatorial blindness.** Ablation breaks down a pair into elements. Memories whose value is genuinely combinatorial (high emergent_residual) may be misread as "neither element matters" when they should be read as "the combination matters." Mitigation: explicit handling of high-residual cases in retrieval ranking.

---

## 13. Ablation Doctrine

Orthogonal ablation is the last primitive between Cerebra's current architecture and the dream/retrain direction working.

It is small in scope (three operations, one metadata record), large in implication (it teaches the system to know which aspects of its memories matter), and disciplined in cost (consolidation-time only, budget-capped, confidence-gated).

The instinct that prompted it — "did X make Y sound better in this orthogonal context, or the other way around?" — is the right instinct. It is the question a system needs to ask itself if it is going to develop understanding rather than pattern-matching.

A memory system that knows which aspects of each memory carry which kinds of value is qualitatively different from a memory system that knows what its memories are about. The first kind learns. The second kind retrieves.

Ablation is the move that gets Cerebra to the first kind.
