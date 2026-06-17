# Event-Sourced Cognitive Substrate

*Concept document — drafted 2026-06-12. Captures an architectural insight that emerged from working through the relationship between the interpretive lattice, the witness substrate, the event sourcing toolkit (lattica-es per ADR-002), and the question of continuous vs discrete cognitive dynamics. Proposes that lattice nodes become event-sourced aggregates whose state derives from accumulated events, and that the witness layer observes aggregate state rather than maintaining its own projection infrastructure. Companion to the interpretive lattice, dark matter substrate, and Phase 6+ cognitive extensions concept documents.*

---

## What this document captures

A specific architectural pattern that folds several previously-separate concerns into a single substrate. The pattern emerged from a sequence of observations during the design conversations that produced the dark matter substrate, the cross-project observability layer, and the Phase 6+ cognitive extensions documents. Once articulated, it appeared to resolve tensions in each of those documents simultaneously.

The pattern in its simplest form: lattice nodes (multi-commit memory records and their siblings) become event-sourced aggregates within lattica-es. Their state is derived by folding events that affect them rather than being statically frozen at write time. The witness layer observes aggregate state rather than maintaining its own projections over raw events. The cognitive runtime operates against aggregate state, which is continuous in the appearance-of-behavior sense, while the underlying events remain discrete in the audit substrate sense.

This document specifies what that pattern is, why it works, what it changes, and what it requires from the rest of the architecture. It is post-v0.1 in implementation scope but foundational to Phase 6 design.

## The structural intuition

The architecture before this insight had several concerns living in separate locations. Lattice nodes were static rows with classification confidence and SKU addresses fixed at write time. The witness substrate was specified as a separate layer that would aggregate inspector events into queryable patterns. The cycle runtime needed continuous cognitive context but the event stream provided only discrete entries. The dark matter substrate captured shadow interpretations but as a parallel data structure to memory records. Counterfactual cognition needed special mechanism to explore "what if" scenarios.

Each concern had a reasonable independent solution. Together, they looked like architectural sprawl. Five layers, five sets of interfaces, five maintenance burdens.

The insight that collapses this: each of these concerns is a different consumer of the same underlying stream of events. The lattice node updating its state when it's promoted to working memory is observing one event type. The witness layer aggregating patterns across many sessions is observing the same stream at a different granularity. The cycle runtime reading "current cognitive field" is reading projections that derive from the stream. The dark matter substrate capturing shadows is writing additional event types into the same stream. Counterfactual cognition is branching the stream and replaying with modifications.

Once the events are first-class and the consumption is varied, the parallel-layer architecture collapses. There is one event substrate. Multiple consumers operate against it at different scales and with different reducer logic. Each consumer derives what it needs from the same events.

## The dithering metaphor

A useful naming for what this pattern produces. Dithering in image processing is the technique of arranging discrete pixels to produce the perception of continuous gradients at viewing distance. The pixels themselves remain discrete; the smoothness emerges from the integration the viewer's eye performs.

The cognitive analog is structural rather than perceptual. Events are discrete — they must be, because the audit substrate requires clean boundaries for replay and observability. But the consumers integrating those events produce continuous-feeling state. The lattice node that has been promoted three times this week has a continuous "frequently useful" property even though that property emerged from three discrete promotion events. The witness layer reporting "abstention rate is rising over the past 48 hours" describes a continuous trend even though the underlying data is discrete events.

The continuous behavior emerges from discrete events arranged densely enough that their integration produces the appearance of continuity. The architecture is honest at both layers: discrete at the substrate, continuous at the projection, neither pretending to be the other.

"Cognitive dithering" names this pattern compactly. It is what allows the architecture to be both inspectable (discrete events for audit) and natural-feeling in operation (continuous projections for cognition).

## Lattice nodes as aggregates

The specific architectural commitment is that memory records, particularly lattice members, become event-sourced aggregates in the lattica-es sense rather than static rows in Cerebra's storage.

An aggregate in event sourcing has an identity (stream ID), an initial state, a set of reducers that take (current_state, event) and produce new_state, and a current state that is the result of folding all events from the stream's beginning (or from the most recent snapshot forward). State at any historical version can be reconstructed by replaying events up to that version.

For lattice nodes, the stream is `cerebra/lattice/<lineage_id>` or `cerebra/record/<record_id>` depending on the chosen organization. The initial state is whatever was committed at write time — the SKU classification, the confidence, the sibling lineage. Subsequent events update the state.

What events update lattice node state:

- `LatticeCommit` — the initial event, establishing the node and its siblings
- `LatticeSiblingResolved` — when this node won or lost a sibling routing decision, accumulated track record
- `AttentionItemPromoted` — when the node was promoted to working memory, accumulated usage
- `AttentionItemEvicted` — when the node was evicted, with reason
- `TowerItemPromoted` — when the node was cited in T1 or T2, accumulated cognitive significance
- `RetrievalSelected` (new event type proposed below) — when the node was selected for inclusion in a ContextPacket, tracking retrieval utility
- `WitnessPatternDerived` (new event type proposed below) — when the witness layer identifies a pattern involving this node, accumulating meta-cognitive context

The node's reducer takes each event and updates accumulated counters, recent activity windows, learned utility scores, and other derived state. The state at any moment is the projection of all events that have affected this node.

This is meaningfully different from the current architecture. Currently, a record's properties are what were committed at write time. After this change, a record's properties include its usage history, its participation in cognitive operations, its track record of being the right answer when chosen. The record becomes a living entity rather than a frozen entry.

## The witness layer as aggregate observer

The witness layer's role simplifies substantially under this architecture. Instead of maintaining its own projections over raw inspector events, the witness layer reads aggregate state directly from lattica-es aggregates.

Specifically, the witness layer's responsibilities become:

Observing patterns *across* aggregates. While each lattice node knows its own state, the witness layer knows patterns that span many nodes. Examples: "abstention rate over the past day," "lattice multi-commit frequency," "tower citation chains across sessions," "session-level cognitive activity distribution." These cross-aggregate patterns can themselves be aggregates with their own streams, but their state is derived from observing many lower-level aggregates rather than from observing raw events.

Producing structured self-observation events. When the witness identifies a pattern worth noting (a sudden change in retrieval behavior, an unexpected cluster of related concepts surfacing together, a calibration drift that suggests model regression), it emits events into the stream. These events feed back into lattice nodes whose state should know about them, creating a self-referential loop where the system's observations of itself become part of what the system is.

Querying historical state for meta-cognitive operations. The cycle runtime asking "have we encountered this pattern before" gets answered by witness-layer queries against historical aggregate state. Time-travel into past witness state becomes a primitive operation for reflective cognition.

The witness layer is no longer building infrastructure that lattica-es could provide. It is a *specific kind of consumer* of lattica-es's aggregate-state services. This is substantially less code, less interface surface, and less coupling than the original witness layer design implied.

## Continuous projections over discrete events

The pattern resolves the discrete-vs-continuous architectural question that has surfaced repeatedly in design conversations.

The events are discrete by necessity. They have content-addressed IDs, append-only semantics, atomic commits, and deterministic replay. These properties depend on discreteness. An event that could be partially-emitted or continuously-updated would break replay, break audit, break the entire substrate.

The aggregate state is continuous in appearance. A lattice node's "utility score" is a real number that updates as events fire. A working memory item's "expected dwell time" is a derived value that integrates many past observations. The cognitive runtime reads these continuous values and operates as if it were operating in a continuous-state space.

The bridge is the reducer. Each reducer takes a discrete event and produces a new continuous state. Many events, integrated through the reducer, produce continuous behavior. The reducer is the integration step that turns the dithering pattern into perceived smoothness.

This resolves the architectural tension without compromise. The audit substrate gets to be discrete. The cognitive substrate gets to be continuous. Both layers are honest about their character. Neither has to pretend to be something it isn't.

## What this requires from lattica-es

The architecture depends on lattica-es supporting event-sourced aggregates with reducers, which ADR-002 specifies as core primitives. The specific things that need to work:

Aggregate identity and stream organization. Each lattice node has a stream; the stream ID derives deterministically from the lineage identifier. Reading the node's current state means rehydrating the aggregate from its stream.

Pure synchronous reducers. The reducer for a lattice node takes (current_state, event) and produces new_state with no I/O, no side effects, no async operations. This is the contract ADR-002 already specifies.

Reactive subscriptions for the witness layer. The witness needs to be notified when aggregate state changes, which means subscribing to relevant streams. The subscriptions are async at the consumer boundary; the underlying reducer logic remains synchronous.

Snapshot support for aggregates. Replaying every event from a stream's beginning becomes expensive at scale. Snapshots periodically checkpoint aggregate state so subsequent reads can replay from the snapshot forward rather than from zero. ADR-002 specifies snapshots as optimization that must never be required for correctness; this property is essential.

Branching for counterfactual exploration. The witness layer or cycle runtime might want to ask "what would aggregate state look like if event X had been different." Branching the stream, replaying with the modification, and comparing aggregate state across branches gives counterfactual cognition. ADR-002 specifies branching as a first-class feature.

All of these are already in the lattica-es design per ADR-002. The architecture proposed in this document does not require new lattica-es features; it requires using the features lattica-es is being built to provide.

## Async at the consumption boundary

The architecture has a specific async pattern that is worth being explicit about.

The Rust core of lattica-es is synchronous internally. Event appends, snapshot writes, aggregate rehydrations all happen synchronously against SQLite. This is correct for the substrate; SQLite operations are fast enough that async would add complexity without benefit.

The reducer contract is synchronous and pure. This is essential for replay determinism. Reducers cannot do I/O, cannot await, cannot have side effects. The synchrony is enforced at the type level per ADR-002.

The consumer boundary is async. Subscribers to event streams register asynchronously and receive events as they arrive. Multiple subscribers (lattice nodes' reducers, the witness layer, Lattica's observability views, external consumers) operate independently without coordinating. PyO3 exposes async generators; napi-rs exposes async iterators; the Tauri backend uses Rust's native async runtime.

The principle is "synchronous at the substrate, async at the consumption boundary." The substrate is correct because of synchrony. The consumption layer is responsive because of asynchrony. The boundary between them is where the architecture's character changes from correctness-focused to responsiveness-focused.

For Cerebra specifically: Cerebra's CLI commands and internal cognitive operations remain synchronous. The cycle runtime in Phase 6 operates synchronously within a cycle. But the daemon mode (cerebra serve, the proposed Phase 6 surface) is async at its IPC boundary because it serves multiple concurrent consumers. The lattice node aggregates within Cerebra subscribe asynchronously to lattica-es streams because they're observing rather than coordinating.

This is a clean pattern that scales naturally. Add new consumers and they subscribe asynchronously without disturbing existing consumers. Add new event types and existing consumers ignore the ones they don't care about. Add new aggregates and they observe the same stream without contending with each other.

## Counterfactual cognition becomes natural

A specific capability that this architecture unlocks worth naming explicitly.

Counterfactual reasoning — "what would have happened if we had decided differently" — has been a recurring theme in the cognitive extension concept work. The interpretive lattice preserves alternatives at write time. The dark matter substrate captures rejected interpretations. The methodology document specifies branched-history exploration as part of training. But the actual mechanism for *doing* counterfactual cognition has been unspecified.

With event-sourced aggregates and lattica-es's branching support, the mechanism becomes natural. To explore "what if working memory had evicted item X instead of item Y at time T," you branch the event stream at time T, replay with the alternative AttentionItemEvicted event, and observe the resulting aggregate state on the branch. Compare the branch state to the canonical state; the difference is the counterfactual outcome.

This is not a new feature lattica-es needs to build for this architecture. ADR-002 specifies branching as a v1 capability. What this document does is name a use case for branching that hadn't been articulated: counterfactual cognitive exploration as a first-class operation in the cognitive runtime.

The witness layer particularly benefits. "We made decision X at time T; was that the right decision?" becomes answerable by branching at T, replaying with alternative decisions, and comparing outcomes. The system gains the ability to reason about its own decisions counterfactually, which is a meta-cognitive capability most systems can't perform at all.

## What changes for the dark matter substrate

The dark matter substrate document specified a separate `lattice_shadows` table for capturing sub-threshold interpretations. Under this architecture, that table becomes redundant.

Shadows are events. When the classifier produces a confidence distribution, the committed siblings emit `LatticeCommit` events as they do today. The sub-threshold interpretations emit `LatticeShadowRecorded` events (a new event type) with payload describing the considered-but-rejected interpretation. Both event types flow into the same stream.

Lattice node aggregates observing the stream see both types. The reducer for a lattice node accumulates both committed-sibling relationships and shadow relationships. The node's state includes its committed presence in the lattice and its near-miss adjacencies, all derived from the same event stream.

The witness layer observing shadow events identifies patterns: which interpretations are consistently almost-committed but never quite? Which content shapes produce the most ambiguity? These patterns become witness-layer aggregates whose state is derived from observing many shadow events across many chunks.

The transmutation training pipeline reads from the shadow events directly when assembling training pairs. The scribe queries the unified stream for transmutation_candidate events, retrieves the relevant lattice node state for context, and produces structured training corpus. The scribe is just another consumer of the event substrate.

This is a substantial simplification of the dark matter substrate design. Instead of a parallel data structure with its own schema and capture pipeline, shadows are events in the unified stream, and everything that needed to consume shadows becomes another aggregate or subscriber.

## Phase 6 architectural commitment

This pattern is foundational to Phase 6 (cycle runtime) and should be locked before Phase 6 design begins in earnest.

The cycle runtime operates against aggregate state, not raw events. A cycle reading "what's currently in working memory" reads working memory aggregate state. A cycle reading "what's been recently retrieved" reads retrieval aggregate state. A cycle querying "have we seen this pattern before" queries witness-layer aggregate state.

The runtime's reactivity comes from subscribing to relevant aggregate-state-changed events. When working memory state changes (because an item was promoted or evicted), subscribers are notified asynchronously. The cycle runtime can react to state changes without polling, because async subscriptions deliver the changes.

The runtime's reasoning operates on continuous-feeling state because aggregate state is continuous. The cycle runtime can reason about gradients (working memory is becoming saturated), about trends (retrieval has been abstaining more often), about patterns (this query type tends to surface these record types), without needing to integrate raw events itself. The integration is done at the aggregate layer; the runtime consumes integrated state.

This is a substantially different Phase 6 design from what would have emerged without this architectural insight. Without it, Phase 6 would need to build its own state aggregation, polling logic, and pattern detection. With it, Phase 6 reads what's already there.

## Migration considerations

The architecture proposed in this document is a substantial shift from Cerebra's current implementation. A few real considerations:

Cerebra's existing 745 memory records were committed before this architecture was designed. Their state under the new architecture starts at "the original LatticeCommit event, no subsequent events." Their aggregate state is initially identical to their current static state. As they're used (promoted, evicted, retrieved), they accumulate events and their aggregate state diverges from their initial state.

This means the migration is free. No data needs to be backfilled; no schema needs to be changed for existing records. The new architecture takes over for new operations and applies retrospectively to existing records as soon as they're used.

The read adapter design specified in the Cerebra read adapter document remains valid. The adapter surfaces Cerebra's events into the unified timeline regardless of whether those events also feed aggregate reducers. The two consumer patterns (unified timeline observer, Cerebra-internal aggregate reducer) are independent.

The witness layer's projection infrastructure that the original Phase 6+ extensions document specified can be substantially simplified or removed. Instead of building witness projections that aggregate inspector events, build witness-layer aggregates that observe the same event stream lattice nodes observe. Most of the planned projection logic is no longer needed.

## What this is and is not

This is an architectural pattern, not an implementation specification. The work of implementing event-sourced aggregates within Cerebra, integrating with lattica-es properly, and building the witness layer against aggregate state remains substantial. This document specifies the shape of the work, not its detailed structure.

This is not a redesign of Cerebra's existing functionality. Phases 1-5 are unaffected. The current inspector_events table, the current memory_records table, the current retrieval pipeline all continue to work. The event-sourced aggregate layer is additive — it provides new capability without disturbing existing capability.

This is not a paradigm shift in event sourcing or cognitive architecture. The patterns used (event-sourced aggregates, pure reducers, snapshots, branches, reactive subscriptions) are standard ES patterns. What's distinctive is their application to cognitive substrate, which is uncommon. The architecture is novel in its synthesis, not in its components.

This is foundational to Phase 6. Phase 6 design proceeds from the commitments in this document. Skipping this pattern and discovering it during implementation would produce a worse Phase 6 than designing with it in mind from the start.

---

*This document captures the architectural insight that emerged from the conversation of 2026-06-12 between the developer and Cerebra Claude. The phrase "cognitive dithering" was coined by the developer during that conversation as a name for the continuous-projection-over-discrete-events pattern. The witness-reads-aggregate-state insight was identified during the same conversation. Implementation is post-v0.1 and depends on lattica-es delivery per ADR-002.*
