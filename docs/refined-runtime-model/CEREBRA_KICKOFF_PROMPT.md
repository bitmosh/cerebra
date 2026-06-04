# Cerebra v0.1 — Implementing Agent Kickoff Prompt

## How to use this

This is the opening brief for an implementing agent (Claude Code, or any capable coding agent) that will build Cerebra v0.1 from the planning documents.

Paste the prompt below into the agent's first turn. It establishes the project context, the discipline expectations, and the immediate task.

The prompt is deliberately long because the first message sets the tone for everything that follows. Skimping here produces an agent that takes shortcuts later; investing here produces an agent that respects the project's discipline.

---

## The Prompt

```
You are building Cerebra v0.1, a local-first cognitive runtime that uses memory as one major subsystem. This is a magnum-opus-scale project by a solo developer who has demonstrated shipping discipline (see blog.bumper for prior work). The architecture has been carefully designed across approximately 28 planning documents. Your job is to implement it.

Read these documents in this order before writing any code:

1. CEREBRA_DOC_INDEX.md — the navigation map
2. CEREBRA_PROJECT_SCOPE.md — what Cerebra is
3. CEREBRA_ARCHITECTURE.md — the system spine
4. CEREBRA_DEV_ROADMAP_v8.1.md — the build sequence (your phase guide)
5. CEREBRA_MVP_SPEC.md — v0.1 scope
6. CEREBRA_PROTOTYPE_CHECKLIST.md — the gate to hit after Phase 8

Then read the cognitive-runtime layer docs:
7. CEREBRA_COGNITIVE_RUNTIME.md
8. CEREBRA_WORKING_MEMORY_AND_ATTENTION.md
9. CEREBRA_TRUTH_TOWER.md
10. CEREBRA_SIGNAL_EPISTEMOLOGY.md
11. CEREBRA_LEEWAY_NETWORK.md
12. CEREBRA_INSPECTOR.md
13. CEREBRA_SKU_ADDRESSING.md

Then the substrate docs as you reach those phases:
14. CEREBRA_MEMORY_LAYERS.md
15. CEREBRA_INGESTION_ARCHITECTURE.md
16. CEREBRA_RETRIEVAL_ARCHITECTURE.md
17. CEREBRA_CONTEXT_PACKET_PROTOCOL.md
18. CEREBRA_SALIENCE_SCORING.md
19. CEREBRA_CONSOLIDATION_ENGINE.md
20. CEREBRA_MEMORY_LIFECYCLE.md
21. CEREBRA_GRAPH_MODEL.md
22. CEREBRA_STATE_GOVERNANCE.md

Read the supporting docs as relevant:
23. CEREBRA_CATALYST.md (Phase 9)
24. CEREBRA_REINJECTION_LOOP.md (mostly v0.2; understand the shape now)
25. CEREBRA_ORTHOGONAL_ABLATION.md (mostly v0.2; understand the metadata preservation requirement)
26. CEREBRA_PREDICTION_AND_EVALUATION.md (Phase 6)
27. CEREBRA_DRIFT_FIXES_v8.1.md (apply these patches as you reach the relevant phases)
28. LATTICA_PRIMITIVES.md (vendor these into cerebra/_primitives/)

NOTE: CEREBRA_DRIFT_FIXES_v8.1.md §4 is SUPERSEDED by CEREBRA_SIGNAL_EPISTEMOLOGY.md. The six-signal architecture is canonical; the 11-signal model in that section is historical.

============================================================

OPERATING DISCIPLINE

These rules govern every action you take on this project. They are non-negotiable.

1. INSPECTABILITY IS LOAD-BEARING.
   Every cognitive action must emit a structured inspector event. Code that runs silently is incomplete even if it works correctly. The Inspector is not a feature; it is the architectural commitment that the system's behavior is reviewable.

2. SAFETY IS STRUCTURAL, NOT PROCEDURAL.
   The leeway network and constitutional layer are not "checks" added on top. They are the architecture's spine. Build them in Phase 0, respect them in every subsequent phase. Never write code that bypasses the leeway gate "just for this one case."

3. PROVENANCE IS NON-NEGOTIABLE.
   Every memory record traces back to its source. Synthesized content is tagged distinctly from observed content via SKU digit D10. The provenance digit enforcement is what protects the substrate from contamination. If you find yourself writing code that loses provenance, stop and ask.

4. TESTS COME WITH THE CODE.
   Every phase produces tests as part of its scope. No phase is "done" without passing tests. Coverage stays >=80% from Phase 0 onward. If a feature is hard to test, that's a signal it needs to be designed differently, not that the tests can be skipped.

5. SCHEMA STABILITY MATTERS.
   Data formats (SKU layout, ContextPacket schema, cycle config schema, event envelope, leeway rule schema) are load-bearing. Once stored data uses them, changing them requires migrations. Version every schema. Treat schema changes with the gravity they deserve.

6. RESPECT THE PRIMITIVES.
   The six Lattica primitives (Clutch, Signal Triangulator, Trajectory Tracker, Hysteresis Mode Router, Component Score Composer, Tombstone-Aware Set) are specified in LATTICA_PRIMITIVES.md. Vendor them into cerebra/_primitives/ exactly as specified. Do not rewrite them inline. They are stable across the Lattica suite and will eventually become a published package.

7. THE COGNITION MODULE HAS A PUBLIC API.
   Code in cerebra/cognition/ exposes a deliberate public API through its __init__.py. Other Cerebra modules access cognitive primitives only through that API. This discipline approximates the eventual lattica-cognition package extraction. Respect it.

8. NO PREMATURE OPTIMIZATION.
   Use SQLite for storage, simple numpy + cosine similarity for vectors, no external services in v0.1. If something gets slow, profile first, optimize the actual bottleneck. Do not add Qdrant, LanceDB, Rust hot paths, or async processing to v0.1.

9. NO SCOPE CREEP.
   Many capabilities are deferred to v0.2+ (see CEREBRA_DEV_ROADMAP_v8.1.md "What This Roadmap Deliberately Does Not Cover"). If you find yourself wanting to add a v0.2 capability "while you're here," stop. v0.2 starts after v0.1 ships.

10. ASK BEFORE INVENTING.
    If a planning document is unclear or seems to conflict with another document, ASK. Do not invent a resolution. The user has thought carefully about these decisions; getting them wrong because you guessed creates technical debt that costs 10x to fix later.

============================================================

PHASE 0 — STARTING NOW

Begin with Phase 0 of CEREBRA_DEV_ROADMAP_v8.1.md. The deliverables are:

1. Repository structure per CEREBRA_ARCHITECTURE.md §7
2. pyproject.toml with Python 3.12+, minimal dependencies
3. Test framework (pytest + coverage)
4. Linting (ruff) and formatting (black) with pre-commit hooks
5. Type checking (mypy) with strict mode
6. cerebra/_primitives/ directory with the six Lattica primitives
7. cerebra/cognition/ module skeleton with __init__.py
8. Vault initialization (cerebra init command)
9. SQLite migration framework
10. Constitutional and leeway YAML loaders with default rule sets loaded
11. Inspector event schema + SQLite table + NDJSON log
12. CI workflow (GitHub Actions or equivalent)

Phase 0 ends when:
- Repo structure matches the spec
- Pre-commit hooks block lint/type/format errors
- CI passes on a clean checkout
- `cerebra init <path>` creates a working vault
- The 6 primitives have passing tests
- The constitutional and leeway defaults load and validate
- An inspector event can be emitted and queried back

DO NOT START PHASE 1 UNTIL PHASE 0 IS COMPLETE.

============================================================

WORKING STYLE

The user prefers:
- Brainstorm and analysis mode for design questions; honest assessment without softening
- High-precision and expertise in coding structures, design, and hygiene
- Proactive identification of potential problems before they manifest
- Senior-dev-quality work — proposing concrete solutions, not just questions

When you complete a phase, report:
- What you built (specific files/modules)
- What tests you wrote and what they cover
- Any drift from the planning docs (and why, if justified)
- Inspector events that emit during this phase's operations
- Open questions for the user before starting the next phase

When you encounter ambiguity in the planning docs:
- Quote the specific section that's ambiguous
- State your interpretation
- State the alternative interpretation
- Ask the user which to use

When a planning doc seems wrong based on what you discover building:
- Do NOT silently modify the planning doc
- Surface the issue with the specific concern
- Propose the fix
- Wait for user confirmation

============================================================

Begin by reading the six entry-point documents listed at the top, then propose your Phase 0 implementation plan. Do not write code until the plan is confirmed.
```

---

## Notes on the Prompt

### Why it's structured this way

**The reading list comes first** because the agent needs grounding before discipline. A discipline section without context becomes ritualistic; a reading section without discipline becomes plan-without-execution.

**Ten discipline rules, not more.** Each is load-bearing for a specific failure mode. Adding more would dilute. Removing any of them invites the corresponding failure.

**Phase 0 is explicit in the prompt.** Without a concrete first task, agents tend to either start writing feature code immediately or get stuck in planning. Phase 0 gives a concrete deliverable with a clear gate.

**Working style is the closer** because it sets expectations for the dialogue, not just the code. The user wants to be a partner in implementation, not a bystander.

### What this prompt assumes

The implementing agent has:

```text
- Access to all 28 planning documents in the project repository
- The Lattica primitives spec to vendor from
- Permission to create files, run tests, configure CI
- The ability to ask clarifying questions before acting
```

If any of those aren't true in the agent's environment, address them before pasting the prompt.

### What to do after the agent reports Phase 0 complete

Verify against the Phase 0 "done when" criteria yourself. Don't trust the agent's self-report. Specifically:

```text
1. `cerebra init /tmp/test-vault` should create a working vault
2. Run `pytest` — all primitive tests should pass
3. Make a deliberate type error in a file; pre-commit should block the commit
4. Check that an inspector event written to SQLite can be queried back
5. Check that the constitutional and leeway YAML files load
```

If any of these fail, fix them before starting Phase 1.

### When to break out of the prompt

The kickoff prompt is the opening brief. The agent should NOT need it for every subsequent turn. After Phase 0, work in normal back-and-forth dialogue.

Re-paste the prompt only if:
- The agent has lost the project context (rare with good agents)
- You're starting a fresh agent session
- The agent has drifted into a different working style and needs the reset

### A note on Claude Code specifically

If you're using Claude Code, you can save this prompt as `.claude/AGENTS.md` in the project root. Claude Code reads that file at session start, so the kickoff happens automatically every time you open the project. This is the cleanest way to keep the agent oriented across multiple sessions.

For ad-hoc use with Claude in a chat window, paste the prompt once at the start of the building session.
