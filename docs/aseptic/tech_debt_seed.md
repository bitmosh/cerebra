---
title: Cerebra Tech Debt — Living Report
last_reviewed: v0.3.5a (Phase 8 close)
---

# Cerebra Tech Debt — Living Report

Functional but known-bad implementation choices. Deliberate deferrals. Architectural shortcuts with a known cost. Implementations that bypass structural principles for pragmatic reasons.

The key test: *"does this work correctly today, and do we know why it will need to change?"*

Every entry has a trigger condition for when it becomes worth addressing. Without a trigger, debt becomes wallpaper.

See `docs/aseptic/LIVING_REPORTS.md` (when scrubbed for Cerebra) for entry format conventions.

---

## Open entries

### TD-001 — Purge workflow audit path

**What it is:** When Cerebra eventually implements purge workflows (memory removal, session deletion, vault cleanup), the audit lookup must read `_fossic/system` stream, NOT the original stream. fossic v0.10.v clarified that `read_one` returns `None` after purge; the `Purged` audit event lives in `_fossic/system` only.

**Why it's deferred:** Cerebra has not implemented purge workflows yet. The v0.1 roadmap doesn't require them.

**Known cost:** If purge is implemented without this awareness, the audit lookup would fail silently or return stale data, defeating the purpose of having an audit trail.

**Trigger:** Cerebra begins designing or implementing any purge workflow (memory record purge, session deletion, vault wipe).

**Evidence:** fossic cross-pollination file `pass-10.v.md` (Cerebra: FYI). fossic spec `FOSSIC_V1_SPEC.md §9.3`.

---

### TD-002 — v0.2 LoRA training resume

**What it is:** Phase 2 LoRA training landed at 46.7% strict accuracy with 0% parse failures (methodology success), but corpus imbalance (RELATIONAL quadrant underrepresentation, zero AGENT training records) is the real blocker. Phase 3 pivot to format corpus via distillation from the instruct variant preceded the bench decision.

**Why it's deferred:** Phase 6/7/8 cycle runtime work prioritized over LoRA improvements. Real-world cycle data will provide better training signal than synthetic balancing.

**Known cost:** Cerebra's signal evaluator currently uses prompt-only Granite 4.1 3B Instruct calls. A trained LoRA would reduce latency and potentially improve consistency, but isn't blocking.

**Trigger:** (a) Corpus imbalance addressed (RELATIONAL and AGENT quadrants populated from actual cycle outputs), AND (b) format corpus distillation from instruct variant prepared.

**Evidence:** `cerebra-phase2-report.md`, `lora_run1_diagnostic_report.md`, `v02_lora_phase2_plan.md`.

---

### TD-003 — Lattica-primitives PyPI extraction

**What it is:** Six shared primitives (Clutch, Triangulator, Trajectory, HysteresisModeRouter, ScoreComposer, TombstoneSet) are vendored into each project's `_primitives/` folder. Extraction to a `lattica-primitives` PyPI package is planned for the 9-12 month horizon.

**Why it's deferred:** Two stable consumers required as criterion. Currently only Cerebra is actively using all six; LumaWeave hasn't started consuming yet.

**Known cost:** Six primitives × N projects = N copies to maintain when changes need to propagate. Low cost in v0.1 (only Cerebra has them); cost grows with consumer count.

**Trigger:** 2+ stable consumers actively using the primitives AND 90-day stability criterion cleared (no breaking changes in primitives for 90 days).

**Evidence:** `LATTICA_PRIMITIVES.md`.

---

### TD-004 — Dark matter substrate implementation

**What it is:** The "dark matter" substrate concept (banked from concept exploration) represents implicit context that influences cognition but isn't explicitly retrieved — analogous to ambient background knowledge.

**Why it's deferred:** Conceptual work; no implementation surface in v0.1. v0.1 retrieval is explicit-only.

**Known cost:** None at v0.1. Future cognitive extensions may need this substrate to handle ambient priors and tacit knowledge.

**Trigger:** Post-v0.1 cognitive extension work begins (specifically, when Phase 9+ cycle configs need implicit context handling).

**Evidence:** `event_sourced_cognitive_substrate.md`, concept docs in `docs/agent/concepts/`.

---

### TD-005 — Witness layer projections (lattica-es aggregate consumer)

**What it is:** The witness layer is the v0.2 cognitive observation mechanism — subscribes to fossic streams, projects cognitive state, surfaces patterns for retrospective analysis. v0.1 ships cycle event emission but no consumer of those streams.

**Why it's deferred:** v0.1 milestone targets cycle runtime functionality. Witness layer is post-v0.1.

**Known cost:** Events emit to fossic streams but no projections consume them yet. Stream data accumulates without analysis surface.

**Trigger:** v0.2 work begins, OR a specific cognitive observation need surfaces during v0.1 usage.

**Evidence:** `event_sourced_cognitive_substrate.md`, Phase 8 close artifacts.

---

### TD-006 — Counterfactual cognition via branching (cognitive use)

**What it is:** Phase 8 ships the branching mechanism (fossic supports branches; LeewayGrantApplied gates branch_creation). But no cycle in v0.1 actually triggers branching for counterfactual exploration. The mechanism is ready; the cognitive use isn't.

**Why it's deferred:** v0.1 cycle configs (simple.planning.v0) are linear. Branching for counterfactual cognition requires more sophisticated cycle configs and Clutch decision logic that Phase 9 ships.

**Known cost:** Branching capability exists but unused. No observable cost at v0.1; capability waits for post-v0.1 cognitive extensions.

**Trigger:** Post-v0.1 cycle config design includes counterfactual exploration (branch action in Clutch decision tree).

**Evidence:** Phase 7 leeway gate action vocabulary, Phase 8 design doc §7.

---

### TD-007 — Cognitive extensions (lenses, frame, methodology, iterative self-improvement)

**What it is:** Five concept documents in `docs/agent/concepts/` describe cognitive extensions: interpretive lattice, archetypal lenses, evaluative frame, iterative self-improvement, cognitive extension overview. ~15,600 words of architectural exploration. None implemented in v0.1.

**Why it's deferred:** v0.1 ships the cognitive runtime substrate. Cognitive extensions live on top of that substrate; they're post-v0.1.

**Known cost:** Substantial conceptual work exists without implementation grounding. Some concepts may need revision when implementation surfaces.

**Trigger:** Post-v0.1 milestone reached AND specific extension prioritized based on real-world usage gaps.

**Evidence:** `docs/agent/concepts/interpretive_lattice.md`, `archetypal_lenses.md`, `evaluative_frame.md`, `iterative_self_improvement.md`, `cognitive_extension_overview.md`.

---

### TD-008 — Crypto-shredding session deletion (consume from fossic v1.1)

**What it is:** Cerebra has no session deletion mechanism for compliance/privacy use cases (e.g., user requests "delete everything from session X"). fossic v1.1 will ship crypto-shredding as the canonical mechanism for irreversible event removal.

**Why it's deferred:** fossic v1.1 hasn't shipped yet; consuming a capability that doesn't exist is wasted work.

**Known cost:** Cerebra cannot honor "irreversibly delete this session" requests today. For v0.1 personal-use single-vault scenarios, this is acceptable; multi-user or compliance-driven scenarios would require it.

**Trigger:** fossic v1.1 ships crypto-shredding AND Cerebra encounters a deletion use case (compliance request, user requests permanent removal, or multi-user vault sharing).

**Evidence:** fossic ROADMAP entry on crypto-shredding (post-v1.0).

---

### TD-009 — OTel GenAI export consumption (when fossic ships exporter)

**What it is:** fossic v1.0.0 polish will ship the OTel GenAI span exporter that consumes Cerebra's cycle event streams and emits spans per the AGENT_TRACE_VOCABULARY.md §8.2 mapping (`gen_ai.cerebra.*` namespacing). Cerebra-side payloads stay as-is; the exporter does the translation.

**Why it's deferred:** Exporter hasn't shipped yet. Cerebra-side has nothing to do until it does.

**Known cost:** Observability backends (Tempo, Jaeger, Honeycomb) cannot consume Cerebra cycle traces today. For local-development usage, this is fine; production observability needs it.

**Trigger:** fossic ships OTel exporter in v1.0.0 polish AND Cerebra has a production-like deployment where observability matters.

**Evidence:** AGENT_TRACE_VOCABULARY.md §8.2 (canonical OTel mapping for Cerebra event types).

---

### TD-010 — Daemon mode (`cerebra serve`)

**What it is:** Cerebra currently runs as a CLI invocation (`cerebra run-cycle`). Long-running daemon mode (`cerebra serve`) would support concurrent cycles, multi-user vault sharing, witness layer subscribers running independently, HTTP/IPC interface for external consumers.

**Why it's deferred:** v0.1 single-cycle CLI is sufficient for personal-use validation. Daemon mode is significant scope.

**Known cost:** Cannot run multiple cycles concurrently. Cannot share vault state across processes without coordination. Witness layer consumers can't subscribe without `cerebra serve`.

**Trigger:** (a) Re-injection requires concurrent execution, OR (b) multi-user vault sharing emerges as a use case, OR (c) witness layer implementation begins.

**Evidence:** `CEREBRA_ARCHITECTURE.md` §6 (State Store) implies multi-process access patterns; daemon mode would expose them safely.

---

### TD-011 — Phase 8 benchmark re-run with realistic LatticeNodeReducer

**What it is:** Phase 8 cycle runtime benchmark used a stub LatticeNodeReducer for aggregate volume testing. Real reducer performance may differ; the 47μs/event PyO3 bridge cost is confirmed but reducer-internal computation isn't yet measured.

**Why it's deferred:** Phase 8 benchmark was scoped to cross-stream concurrency validation, not reducer performance.

**Known cost:** Unknown performance characteristics for the real lattice node aggregate. v0.1 uses lattice nodes lightly (mostly retrieval-time access); concerns surface when lattice writes scale.

**Trigger:** Post-v0.1 work that touches lattice reducers (Phase 10 consolidation may; Phase 11 graph export may; v0.2 work definitely will).

**Evidence:** `fossic_aggregate_volume_benchmark_spec.md` and its executed results.

---

### TD-012 — Pre-action constitutional rule shape design

**What it is:** Phase 7 ships LeewayPreActionGate with composition-by-union semantics. Constitutional rules load and are evaluated, but `ConstitutionalRule.forbids()` always returns False in v0.1 (DEV-009). Existing constitutional rules are output analyzers (post-action), not pre-action blockers.

**Why it's deferred:** No actual use case for pre-action constitutional blocking in v0.1. Designing the rule shape speculatively would produce wrong abstractions.

**Known cost:** The leeway gate provides composition-by-union but no constitutional override path. If a specific safety case emerges that needs pre-action blocking, the rule shape design becomes urgent.

**Trigger:** A real safety case requires pre-action constitutional blocking (e.g., a Cerebra deployment encounters a class of cycles that need to be hard-stopped before action, beyond what leeway rules can express).

**Evidence:** Deviation log DEV-009 (v0.3.2), Phase 7 governance audit.

---

### TD-013 — requires_review HITL infrastructure

**What it is:** Phase 7 `GateDecision.review_required_by` field exists but is never populated in v0.1 (DEV-010). No HITL review flow exists; the gate is two-state (permitted/forbidden).

**Why it's deferred:** No HITL flow exists in Cerebra. Adding `requires_review` decision without a consumer is dead weight.

**Known cost:** Cycles cannot pause for human review. For autonomous v0.1 operation, this is correct; collaborative or oversight use cases need it.

**Trigger:** HITL flow design begins for v0.2, OR a specific cycle config requires human approval before specific actions.

**Evidence:** Deviation log DEV-010 (v0.3.2), `GateDecision.review_required_by` field schema.

---

### TD-014 — Aseptic-style continuous instruments full adoption

**What it is:** Cerebra has lightweight Aseptic adoption (this file, POLISH_DEBT.md, PASS COMPLETE template addition). Full Aseptic includes formal supervisor passes, blast-radius per pass, cross-pollination per pass, formal ADRs, agent briefing fragment.

**Why it's deferred:** v0.1 work has higher priority than methodology investment. Lightweight adoption captures highest-value pieces (legible debt, missing-from-git prevention).

**Known cost:** Cerebra produces less structured per-pass data than full Aseptic would. The eventual Aseptic MCP server has less Cerebra contribution data to work with.

**Trigger:** Post-v0.1 milestone reached, AND Cerebra's coordination surface has expanded (e.g., LumaWeave actively consuming Cerebra output, multi-agent parallel passes on Cerebra itself).

**Evidence:** `aseptic_methodology_rundown.md`, fossic's `docs/aseptic/` reference implementation.

---

### TD-015 — Cycle outputs don't influence retrieval until consolidation

**What it is:** Phase 8 Decision 1 — episode records live in `cycle_episode_records` (separate table from `memory_records`). Retrieval pipeline queries `memory_records` only. Therefore cycle outputs are not retrievable until Phase 10 consolidation promotes them.

**Why it's deferred:** Phase 8 scope decision. Phase 10 explicitly will close this gap.

**Known cost:** Multi-cycle usage between Phase 8 close (v0.3.5a, current) and Phase 10 close sees episodes existing but not retrievable. For v0.1 single-cycle demonstration, no impact.

**Trigger:** Phase 10 consolidation work begins.

**Evidence:** Deviation log DEV entry for D1 strategy (v0.3.5a), Phase 8 close artifacts.

---

### TD-016 — ContinuationBundle mechanism unused until Phase 9

**What it is:** Phase 8 Step 3 shipped ContinuationBundle + BundleDistiller as a callable mechanism. No cycle in v0.1 invokes it (no Clutch action triggers continuation). Phase 9 wires the trigger.

**Why it's deferred:** Step 3 vs Phase 9 line drawn explicitly. v0.1 cycle configs don't require continuation.

**Known cost:** Continuation mechanism exists but produces no bundles in v0.1. Test coverage demonstrates the mechanism works; production usage waits for Phase 9.

**Trigger:** Phase 9 Clutch engine implementation.

**Evidence:** Phase 8 Step 3 kickoff, Phase 8 close artifacts.

---

### TD-017 — Citation parsing is best-effort regex

**What it is:** Phase 8 v0.3.5a uses regex-based citation extraction. If LLM doesn't use the exact citation format, citations aren't extracted; salience boost silently does nothing.

**Why it's deferred:** v0.1 LLM citation format is convention-based, not enforced. Stricter parsing would fail more often.

**Known cost:** Salience boosts are unreliable when LLM citation format drifts. Episode records still persist; only the cross-reference effect is degraded.

**Trigger:** v0.2 cycle configs need structured citations (e.g., JSON-mode output with explicit cited_records field), OR observed citation extraction failure rate is high.

**Evidence:** Phase 8 v0.3.5a deviation log entry, CycleRuntime._extract_citations.

---

## Resolved entries

(none yet — Phase 8 close is the first formal review)

---

*Last reviewed at v0.3.5a (Phase 8 close). Next review: Phase 9 kickoff, or supervisor pass when triggered.*
