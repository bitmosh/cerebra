# Cerebra Phase 2 — Second-Round Consultation

## What's changed since your last report

Your first consultation (`phase2_response.md`) correctly identified Qwen 3.5 9.7B and thinking mode as the latency problem. We disabled thinking and re-ran calibration. Result is in `cerebra-phase2-report.md`. The latency fix worked cleanly (8s/call vs 2min/call). But the accuracy result tells us we have a deeper problem than throughput.

This second consultation is focused — we know what we don't know now. We need your read on three specific decisions before bandit takes any more action.

Re-read your own first report and the new post-calibration report before answering. Also re-read:

- `tests/fixtures/sku_fixtures.py` — full fixture set
- `cerebra/cognition/sku_classifier.py` — the v1.1.0 prompt
- `cerebra/cognition/llm_adapter.py` — current adapter (think:false should be present now per bandit's v1.2.0)
- `docs/refined-runtime-model/CEREBRA_SKU_ADDRESSING.md` — quadrant structure for the two-pass design
- `docs/agent/deviations/v0.1.0.md` — running deviation log

You're welcome to probe the proxy and Ollama directly. Worth verifying that the v1.2.0 adapter actually has thinking disabled and that bandit's report numbers are reproducible — run a small probe yourself if useful.

---

## Decision 1 — The three flagged fixtures

Your first report flagged three fixtures as having labels the model's "wrong" answer could defend: `clear_04`, `clear_10`, `hard_08`. Look at each in `sku_fixtures.py` carefully.

For each of the three, give a verdict in this exact form:

```
fixture_id: <id>
content: <quote the content>
current label: <D1Category>
model's answer: <D1Category>
verdict: KEEP | RELABEL_TO_X | MARK_AMBIGUOUS
reasoning: <2-4 sentences explaining the verdict>
```

Then look at the OTHER 27 fixtures with the same eye. Are there additional fixtures where the label is more defensible than rigorous? List any you find with the same format. We want to know the true baseline accuracy after fixture quality is normalized, separate from prompt quality.

Be a strict reviewer. The point is to know whether the model is getting 47% on a clean test or 47% on a test with maybe 5-7 ambiguous labels. These are very different situations.

---

## Decision 2 — Two-pass hierarchical, designed concretely

Your first report recommended hierarchical two-pass classification (quadrant first, then within-quadrant). Make this concrete enough that bandit can implement it without more design discussion.

Specifically:

**Quadrant taxonomy.** The SKU spec organizes the 16 D1 categories into 4 quadrants (Empirical / Generative / Normative / Relational). Confirm the mapping from `CEREBRA_SKU_ADDRESSING.md` and reproduce it here. If you think a different quadrant mapping would be more model-discriminable, propose it with reasoning.

**Coarse prompt (Pass 1).** Write the full prompt that selects a quadrant. Goal: short, fast, high-accuracy. Include the actual instruction text, JSON output shape, and one-line description per quadrant. Optimize for the model NOT thinking-deliberating — instructions should be pattern-friendly rather than reasoning-demanding.

**Fine prompts (Pass 2, one per quadrant).** Four prompts, one per quadrant. Each only has to discriminate between the 4 categories in its quadrant. Include actual prompts in full. These can include the disambiguation rules from v1.1.0 — but each prompt only needs the rules relevant to its quadrant's confusable pairs.

**Routing logic.** When does Pass 2 NOT fire? (E.g., if Pass 1 returns confidence ≥ 0.95 AND the quadrant has only one viable category given the chunk's other signals, is the SKU just the quadrant default?). Or does Pass 2 always fire? Argue your choice.

**Schema impact.** What changes does the `sku_assignments` table need? Currently it stores `raw_scores_json` (all 16 scores). With two-pass: do we store both Pass 1 quadrant scores AND Pass 2 within-quadrant scores? Or collapse them into a single denormalized scores object? What's the right data model for re-classifying when prompt_version bumps?

**Predicted accuracy.** Given what you saw in the calibration result, predict: what overall top-1 accuracy do you think this gets? Argue from the failure modes you observed. Include best case, expected case, and worst case.

**Caveats.** What does two-pass NOT fix? If the underlying problem is "model can't read instructions about intent vs surface form," two-pass might just produce two layers of the same problem. Argue honestly whether two-pass is solving a real failure mode or just shifting it.

---

## Decision 3 — Temperature stochasticity and reproducibility

Your first report noted that two runs of the same fixtures gave 47% and ~33% accuracy. Reproducibility matters for Cerebra because Phase 3+ depends on stable SKUs.

Three sub-questions:

**(a) Diagnose the cause.** Is the variance from temperature 0.1 + JSON-mode token sampling? From the model's internal thinking-state initialization? From something else? Run a probe if useful — call the classifier on the same chunk 5 times in a row with temperature=0, temperature=0.1, and (if applicable) seed parameter set. Report the variance you see and propose the cause.

**(b) Determinism options.** Rank these by likely-effectiveness:

1. Temperature 0.0 (pure greedy decoding)
2. Temperature 0.1 + fixed seed parameter (if Ollama supports it)
3. Full JSON schema grammar constraint (not just `format:"json"`)
4. Store sampling parameters in `sku_assignments` so re-runs are conditionally reproducible
5. Accept stochasticity and use multi-sample consensus (call N times, take majority)

For each: would it work, what's the cost, does Ollama actually support it.

**(c) The pragmatic recommendation.** If we can't achieve true determinism, is "stable SKUs within a single backfill run, may differ across re-runs" acceptable for v0.1? Or does Phase 2 close-out need to ship deterministic-by-construction?

---

## Decision 4 — The strategic question

Step back from the tactics. Given everything you've now read about Cerebra and seen in the calibration data, the strategic question is:

**Is the D1 taxonomy itself a good fit for what a 7-10B parameter local model can reliably do?**

The 16 cognitive categories are philosophically rich — they're drawn from epistemological tradition (Aristotelian categories, Buddhist analytical typology, Peirce's modes of inference). But they ask the model to discriminate based on *cognitive function and authorial intent*, which is a semantic move that small models without specific training cannot reliably make from surface text.

Three honest paths:

**Path X: Keep the taxonomy, accept imperfect classification, plan LoRA in v0.2.** The taxonomy is right; the model is the limit. Ship at whatever the two-pass hierarchical achieves (60-70%) and document the v0.2 fine-tuning track. Phase 3+ tolerates the imperfection because retrieval uses multiple signals.

**Path Y: Revise the taxonomy to be more model-discriminable.** Recognize that the 16 categories are too semantically deep. Reduce to 8 categories (or even just the 4 quadrants) for v0.1. Ship with simpler categorization that the model can do reliably. Revisit richer taxonomy when fine-tuned model is available.

**Path Z: Hybrid — keep the 16-category taxonomy but make D1 a derived field from richer underlying signals.** Instead of the model classifying D1 directly, have it produce structured outputs (verb voice, presence of imperative mood, content category nouns, etc.) and derive D1 from those rule-based. The model does easy structured extraction; Cerebra does the semantic assignment from features.

For each path, honestly assess:
- What's the cognitive integrity cost (does it weaken Cerebra's architecture)?
- What's the schedule cost (delays to Phase 3+)?
- What's the v0.2 LoRA implication (does this path make fine-tuning easier or harder)?
- Which architectural commitments would this lock in?

Then pick one. Be specific about which path you'd take and why, and what evidence would change your mind.

---

## What we want from you

A single markdown document with sections matching the four decisions. Where you change your mind from your first report, say so explicitly — the data from the post-calibration test is new information and shifting on it is a feature, not a flaw.

Be substantive on Decision 4 specifically. The first three are tactical. The fourth is strategic and we need real engineering judgment, not diplomatic hedging.

Where you're uncertain, be specific about what would resolve the uncertainty. "I'd want to see X before being confident about Y" is more useful than "it depends."

Quote code or fixture content directly when it's load-bearing for your argument. Don't refer abstractly when you can point precisely.

Time horizon: take whatever you need.
