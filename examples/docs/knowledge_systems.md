# Patterns in Knowledge-Intensive Systems

Knowledge-intensive systems store, retrieve, and reason over structured information
to support decision-making. This document surveys the key architectural patterns.

## Memory tiers

Well-designed knowledge systems distinguish between tiers of memory:

- **Working memory** — active context for the current task; small, fast, contested
- **Episodic memory** — records of past events and outcomes
- **Semantic memory** — durable facts and relationships, indexed for retrieval
- **Procedural memory** — learned strategies and heuristics

Each tier has different access patterns, freshness requirements, and eviction rules.
Conflating them leads to systems that either overflow with stale data or lose
important context at the wrong moment.

## Retrieval over recall

Human memory is reconstructive, not archival. Knowledge systems that try to
"remember everything" tend to perform worse than systems designed around retrieval:
- Index for the queries you will actually ask
- Score candidates by relevance, not insertion order
- Rank by composite signal (lexical + semantic + structural)

## Signal-based evaluation

Rather than a single quality score, robust systems evaluate outputs across multiple
independent signals:

- **Coherence** — internal consistency of the output
- **Groundedness** — anchoring in evidence from memory
- **Relevance** — alignment with the stated goal
- **Precision** — specificity over vagueness
- **Generativity** — novel contribution beyond retrieval
- **Epistemic humility** — calibrated uncertainty

Orthogonal signals expose failure modes that composite scores hide.

## Structural safety

Knowledge-intensive systems operating autonomously need structural guardrails:

- **Capability bounds** — scope of actions the system is permitted to take
- **Leeway grants** — temporary permission to exceed bounds with justification
- **Constitutional constraints** — inviolable rules that override all other logic

Treating safety as a structural property (not a post-hoc filter) makes failure modes
explicit and auditable.

## Graph-native events

Cognitive state is naturally a graph: memory records, retrieval paths, cycle steps,
and evaluation signals all form typed edges between typed nodes. Emitting events in
a graph-native format means visualization and debugging come for free.

## Local-first

Running inference locally (Ollama, llamafile, etc.) removes cloud dependency,
eliminates per-inference cost at scale, and keeps sensitive data on-device. The
trade-off is hardware requirements and the need to manage model weights.
