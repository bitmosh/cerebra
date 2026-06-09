# Counsel/Swarm Cognition

*Drafted 2026-06-05. Status: architecture concept for v0.2+. Not yet on dev path.*

## The intuition

This is how people actually handle ambiguity. We don't run a single linear thought process and commit to its first output. We mentally form a model of each way a situation can go, see which scenarios fizzle out and which lead to reasonable conclusions, and compare the surviving paths.

Single-model linear thought breaks when the model gets stuck in the stuff that fizzles out and can't reach the part where reasonable conclusions are compiled and compared. The fix isn't a better single model — it's running multiple perspectives in parallel and treating their disagreement as signal.

A counsel of small models can handle ambiguity that a single bigger model can't. Not because they're individually smarter, but because the structure of multi-perspective deliberation matches the shape of the problem.

## The four-tier structure

**Tier 1 — Single fast classifier.** Most chunks get classified once by the cheapest reliable model. Fast, low cost. For clear cases this is enough; the answer is obvious and one model gets it right.

**Tier 2 — Disagreement detection.** When confidence is low, OR the chunk has features known to confuse the primary model, OR catalyst signals "this needs more care" — escalate to the counsel. The escalation decision is itself a cognitive choice, made by the system not the model.

**Tier 3 — The counsel votes.** N small models classify the same chunk independently. Their disagreement *pattern* is the signal:

- All 4 agree → confident answer
- 3 agree, 1 dissents → high confidence with disambiguation note
- 2/2 split → genuine ambiguity, flag for human review or store both
- 1/1/1/1 → chunk content is too ambiguous; mark as needing reformulation

**Tier 4 — Reasoning extraction.** When the counsel splits, each model produces a short rationale or feature list. The system can detect *why* they disagreed — were they reading different features of the text? Did some weight surface vocabulary while others weighted structure? The disagreement isn't noise; it's diagnostic data.

## Why this is faster than single-model

Counter-intuitive but real. The naive expectation is that more models = more work. Actual cost calculus:

- 3B model: ~3s/call
- 8B model: ~8s/call
- 9B model: ~10s/call

Running 4 different 1-3B models in parallel against an ambiguous chunk costs about the same wall-clock time as one 9B call, because they execute concurrently on the GPU. But you get 4 votes for the price of one slow call.

For 745 chunks, if 20% are ambiguous and need counsel-tier evaluation:
- 596 chunks × single 3B call (~3s) = ~30 minutes
- 149 chunks × 4-model counsel (~5s parallel) = ~12 minutes
- Total: ~42 minutes

Compare to the 5+ hours we hit on a single 9B model running everything through thinking-mode. The swarm isn't slower than single-model classification. It's faster AND produces better data.

## How it maps onto Cerebra's existing architecture

This isn't a parallel system to invent. It composes with existing pieces:

**The catalyst decides when to escalate to the counsel.** Catalyst already decides which strategy to use for a problem; "use the counsel" is just one strategy. Catalyst's signal: confidence below threshold, or chunk has features tagged as historically confusable.

**The clutch's signal-to-action mapping naturally extends.** Right now: signal state → typed action. Extension: counsel disagreement pattern → typed signal (consensus / split / fragmented). This becomes input to other decisions downstream.

**The inspector logs the counsel votes per chunk.** This is the corpus for understanding model behavior over time. Which model is best at PRINCIPLE? Which is best at MECHANISM? After 745 chunks, you'd have rich per-model expertise data.

**The signal pipeline can use counsel agreement as a meta-signal.** Counsel consensus IS a confidence signal that's much more reliable than any single model's self-reported confidence (which we've seen is poorly calibrated — Qwen 3.5's 80-82% hallucination rate makes single-model confidence essentially useless).

## The deeper reframe

Counsel mode isn't a fallback for when the single model is bad. It's a different cognitive mode entirely.

Single linear thought is appropriate for clear cases. Deliberation among multiple perspectives is appropriate for ambiguous cases. The system should know which mode it's in.

This is the System 1 / System 2 distinction at the model level rather than the inference-mode level:
- **System 1** = single fast model, pattern-matching, low cost
- **System 2** = counsel deliberation, multiple perspectives, higher cost

The catalyst decides which mode the moment calls for. This is the same architectural decision as "should this be a thinking-mode call or a fast call?" — but answered with model selection rather than internal-thinking-toggle. Better, because we control the architecture; we don't just hope the model's internal thinking is helpful.

## Why this is different from ensembling

Standard ML ensembling: run N models, take majority vote, ship the consensus answer. The output is one answer.

Counsel cognition: run N models, examine the *pattern* of agreement, treat disagreement as diagnostic information about the input. The output includes the disagreement structure, not just the consensus.

A 2/2 split in ensembling is bad — the ensemble failed to produce a confident answer. A 2/2 split in counsel cognition is *information* — the chunk genuinely sits on a category boundary; the system should treat it differently from a chunk where all four models agreed.

This is closer to how human committees work than how ML ensembles work. A committee where 4 out of 5 experts agreed reports the consensus AND the dissent. The dissent matters because it tells you what could go wrong with the consensus answer.

## Models that compose well in a counsel

Not every model is a good counsel member. The criteria:

- **Architectural diversity.** Don't run 4 copies of the same model with different prompts — they share the same failure modes. Run models from different families: Qwen, Granite, OLMo, SmolLM.
- **Comparable scale.** Don't mix a 0.5B with a 14B — the larger one dominates by default. Counsel members should be roughly peers.
- **Reliable output formats.** Counsel disagreement only works if you can compare outputs. Models that occasionally return malformed JSON poison the analysis.
- **Different training emphases.** A model trained for instruction-following + a model trained for reasoning + a model trained for code + a model trained for general chat will see the same text differently. That's a feature.

The minimum viable counsel: 3 models from different families, all in the 1-4B range, all with reliable structured output. Add more later if 3 isn't enough disagreement signal.

## Per-model expertise tracking

The interesting downstream consequence: over many calls, the system can learn which model is best at what.

After 745 backfilled chunks with counsel evaluation:
- Granite Micro might be best at TECHNIQUE and PROCEDURE (instruction-following emphasis)
- SmolLM3 might be best at CONSTRAINT and PRINCIPLE (training on rules/policies)
- Qwen 4B might be best at OBSERVATION and EVENT (general-coverage capability)
- OLMo 7B might be best at RELATION and DEPENDENCY (academic-source training)

This becomes routing data. The next time a chunk's coarse classification points toward CONSTRAINT, the system gives extra weight to SmolLM3's vote. Counsel decisions become weighted by per-model expertise.

This is v0.3+ work. But the inspector should capture per-model votes from day one of counsel mode, so the data is there when we want to mine it.

## When to NOT use the counsel

Worth being explicit about. Counsel mode is expensive (4 model calls vs. 1) and complex (disagreement analysis). It's not the default; it's the escalation.

Don't use counsel for:
- Clear cases where catalyst confidence is high
- Tasks where speed matters more than quality (real-time interactive use)
- Cases where the disagreement signal won't be acted on (no point gathering data nobody reads)

Use counsel for:
- Catalyst-flagged ambiguous chunks during backfill
- Chunks with features in the historically-confused list
- Re-classification of low-confidence v0.1 assignments after model improvements
- Any case where the cost of being wrong is high enough that 4× compute is worth it

## Implementation sketch (not specification)

For v0.2 or v0.3, the rough shape:

```
class CouncilClassifier:
    def __init__(self, members: list[LLMAdapter], catalyst: Catalyst):
        self.members = members  # 3-5 LLM adapters from different families
        self.catalyst = catalyst
    
    def classify(self, chunk) -> ClassificationResult:
        # Tier 1: try single model first
        primary_result = self.members[0].classify(chunk)
        
        # Tier 2: catalyst decides if escalation is warranted
        if self.catalyst.should_escalate(primary_result, chunk):
            return self._council_classify(chunk)
        return primary_result
    
    def _council_classify(self, chunk):
        # Tier 3: parallel council vote
        votes = parallel_map(lambda m: m.classify(chunk), self.members)
        
        # Tier 4: analyze disagreement pattern
        pattern = analyze_disagreement(votes)
        
        if pattern == "consensus":
            return votes[0]  # all agreed
        elif pattern == "majority":
            return weighted_synthesis(votes)
        elif pattern == "split":
            return ambiguous_result(votes)  # 2/2 or fragmented
        # else: kick to human review or store as too-ambiguous
```

This is a sketch, not a spec. The actual implementation needs to handle parallel inference safely, deduplicate identical votes, weight by per-model expertise once that data exists, and integrate with the inspector for vote logging.

## Connection to per-pair disambiguation

The per-pair disambiguation insight composes naturally with counsel mode. When the counsel disagrees, the disagreement is usually between two specific categories (MECHANISM vs TECHNIQUE, not random). The boundary-specific diagnostics for that pair can be applied to the counsel votes to derive a more refined answer.

In other words:
- Single-model + per-pair disambiguation = better single-model classification
- Counsel mode + per-pair disambiguation = each member's vote evaluated against the relevant boundary's diagnostics, then synthesized

The two ideas multiply rather than add.

## Diverse failure modes — empirical support from calibration data

The multi-model calibration runs (Round 1 + Round 2) produced data that directly supports the counsel approach. Specifically: **different models miss different fixtures**, with limited overlap in failure modes.

For example, Qwen 3.5 9B and Granite 4.1 3B both scored 58% partial accuracy at baseline, but their miss lists were substantially different:

- Both models miss: clear_07, clear_11, hard_01, hard_02, hard_03, hard_04, hard_05, hard_07, hard_11
- Qwen 9B uniquely misses fixtures Granite 3B gets right
- Granite 3B uniquely misses fixtures Qwen 9B gets right

A counsel including both models would correctly classify fixtures that either alone misses — by virtue of the other model getting it right. The Round 1 + Round 2 data (13 models × 30 fixtures × 3 runs each = 1170 individual classifications with perfect determinism) provides the substrate for selecting counsel members in v0.2+ based on failure-mode diversity, not just on individual accuracy.

The original observation from Round 1 also held in Round 2: **5 fixtures had 0 of 13 models classify correctly.** The fixture audit (`docs/agent/fixture_audit_round2.md`) determined that these were label issues, not model failures — when 13 architecturally diverse models converge on a different answer than the label, the label is more suspect than the models. This is the inverse of the usual ML failure analysis (where consensus failure is treated as a hard problem); for counsel cognition, consensus failure is diagnostic about the test data, not the test takers.

When v0.2 counsel mode comes online, the candidate selection should weight by failure-mode diversity. Two 60%-accurate models with disjoint failure modes are more useful than two 70%-accurate models with overlapping failure modes. The 1170-classification dataset is the empirical foundation for this selection.

## Open questions

- How many counsel members is enough? 3? 5? When do diminishing returns hit?
- How do you handle counsel members with different output schemas? Force conformance, or have an adapter layer?
- Can the catalyst itself be a model that learns when to escalate, rather than a hardcoded rule?
- Should the counsel sometimes include the same model with different prompts, or always be different models?
- How is per-model expertise data stored and queried? Per-category? Per-feature? Both?

These are v0.3 design questions. For v0.2 the simpler implementation (fixed 3-model counsel, hardcoded escalation rules, equal voting weight) is sufficient.

---

*See also: `system1_system2_at_model_layer.md` for the cognitive-mode framing. `per_pair_disambiguation.md` for the boundary-specific diagnostics this composes with.*
