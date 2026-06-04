# Cerebra — Open Questions (Resolved)

## Status

All six open questions from v8.1 planning have been resolved. This doc preserves the resolutions for the record and to maintain traceability.

For ongoing or future open questions, see project notes or a new `CEREBRA_OPEN_QUESTIONS_v0.2.md` when v0.1 prototype reveals new questions.

---

## Q1. Leeway Network — Consultation Timing  ✅ RESOLVED

**Decision:** Option C — pre-action gate + post-action audit, with phase declared per rule.

**v0.1 implementation:** pre-action only. Post-action audit deferred to v0.2 when content-evaluation pipelines are richer.

**Documented in:** `CEREBRA_LEEWAY_NETWORK.md` §7

---

## Q2. Inspector — Rendering Boundary  ✅ RESOLVED

**Decision:** Option B with future Option C — CLI structured event log in v0.1, eventual frontend as separate project starting ~4 days after v0.1 ships. LumaWeave handles rich visual rendering.

**Frontend approach:** custom-rolled. May incorporate winning patterns from open-webui. Independent codebase, communicates with Cerebra's local API.

**Long-term aspiration:** live cognitive process rendering tied into LumaWeave's graph view.

**Documented in:** `CEREBRA_INSPECTOR.md` §3 and §12

---

## Q3. Signal Composition — Categories To Compress  ✅ RESOLVED (reframed)

**Decision:** Neither A nor B nor C. The question was reframed at the user's direction toward an epistemologically grounded signal architecture.

**Resolution:** six signals derived from the perennial threads (university-level logic, philosophy, contemplative traditions, LLM failure modes):

```text
COHERENCE          ← internal consistency thread
GROUNDEDNESS       ← grounding in evidence/experience thread
GENERATIVITY       ← productive tension thread
RELEVANCE          ← fit to purpose thread
PRECISION          ← clarity of distinction thread
EPISTEMIC HUMILITY ← awareness of own limits thread (NEW; load-bearing)
```

Plus CONFIDENCE and SIGNAL_STRENGTH as triangulating multipliers.

**This is more than a compression of the 11-signal list — it's a foundational reframe of what the signal pipeline measures.**

**Documented in:** `CEREBRA_SIGNAL_EPISTEMOLOGY.md` (new doc)

**Deprecates:** `CEREBRA_DRIFT_FIXES_v8.1.md` §4 (marked superseded)

---

## Q4. Prediction-Error Thresholds — Tunability vs Defaults  ✅ RESOLVED

**Decision:** Option C — committed defaults exposed as cycle-config overridable parameters from day one.

```yaml
prediction_error_thresholds:
  noise_band:    0.10
  notable_miss:  0.25
  severe_miss:   0.40
```

**Documented in:** `CEREBRA_DRIFT_FIXES_v8.1.md` §5

---

## Q5. Lattica Primitives — Packaging Discipline  ✅ RESOLVED

**Decision:** Vendor-for-now per recommendation. Python first. Rust possible later for hot paths.

**Implementation:**

```text
Each Lattica project has a _primitives/ directory with canonical copies
Canonical source lives initially in Cerebra subdirectory
Extraction to lattica-primitives PyPI package when criteria are met
   (two consumers, 90+ days production, stable interfaces, external interest)
Estimated extraction: 9-12 months post-Cerebra v0.1
```

**Documented in:** `LATTICA_PRIMITIVES.md` §4 and §5

---

## Q6. Cycle Vocabulary Granularity  ✅ RESOLVED

**Decision:** Option B — shared base vocabulary + per-cycle additions. Evolve toward hierarchical (Option C) as patterns emerge.

**Documented in:** `CEREBRA_CATALYST.md` §5 (action vocabularies) and `CEREBRA_DRIFT_FIXES_v8.1.md` §3 (clutch action grouping)

---

## What Remains Open

No high-confidence design questions remain for v0.1.

Questions that will emerge during implementation (expected, normal):

```text
Specific subcategory schemas for each of the 16 SKU categories
   - Currently only the most-used 4-5 categories need subcategory layouts
   - Defer to post-prototype when real ingestion reveals usage patterns
Specific clutch rule weights and thresholds
   - Need real cycle data to tune
   - Reasonable defaults specified; tuning in v0.2
Specific catalyst vocabulary entries per cycle config beyond Bons.ai ideation
   - Build cycle configs as needed; not all in v0.1
Specific cross-product entries for digit 4 relationship axis
   - The 16 relationship types are pinned; specific usage patterns
     will emerge from real memories
```

These are expected refinements, not design questions. The architecture supports them; the specific values get filled in from evidence.

---

## v0.1 Open-Question Status: clear

The architecture is ready for implementation. New questions raised by implementation should be logged in a new `CEREBRA_OPEN_QUESTIONS_v0.2.md` document rather than appended here, so the v0.1 record stays stable.
