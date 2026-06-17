# Cross-Project Observability

*Infrastructure document — drafted 2026-06-12. Specifies how observability flows across the Lattica project ecosystem. Builds on the event sourcing toolkit revision document for the substrate; specifies how Lattica acts as the observation hub and how OpenTelemetry provides the cross-project standard format.*

---

## What this document addresses

The Lattica suite has multiple projects (Cerebra, LumaWeave, Policy Scout, the LLM hosting stack, the discord-bot, potentially Bons.ai and Rhyzome) that all produce structured cognitive activity worth observing. Each project has its own internal logging and event capture. The cross-project question is how observation flows between them — how a user looking at Lattica's dashboard sees what is happening across all projects, how a developer debugging one project benefits from visibility into another, how training methodology can extract signal from operation across the ecosystem rather than from a single project's events in isolation.

The straightforward approach is each project building its own observability surface and Lattica calling each one's API. This is fragile, requires coordination on every cross-project query, and produces inconsistent observability experiences. The approach this document proposes is that all projects emit observability data in a single standard format (OpenTelemetry), that the event sourcing toolkit provides the substrate where that data accumulates, and that Lattica reads from the unified stream rather than from per-project surfaces.

The result is a single observability layer that scales with the ecosystem. Adding a new project to Lattica's view becomes a matter of having that project emit OTel-formatted events; no per-project integration work is needed in Lattica beyond that.

## The substrate: event sourcing toolkit + OpenTelemetry

The event sourcing toolkit (revised to Rust core with Python and TypeScript adapters) provides the persistent event log. Each project writes its cognitive events through the toolkit; the events accumulate in SQLite either per-project (embedded mode) or across projects (shared-file or daemon mode).

OpenTelemetry provides the wire format and the semantic conventions. The toolkit's Rust core has OTel export capability built in (Rust has mature OTel libraries). When OTel export is enabled, events written through the toolkit also emit as OTel spans, with the toolkit's structural concepts (streams, aggregates, events) mapping onto OTel's structural concepts (traces, spans, attributes).

The mapping is natural. A stream maps to a trace — a logical sequence of related activities. An aggregate command maps to a span — a discrete operation with a start and end. Events within the stream become events on the span (OTel calls them "span events" — non-blocking annotations on a span). Cross-stream relationships (a retrieval that influenced a working memory promotion) become span links.

The mapping is opinionated; projects can override it via configuration. The default works for most cases. The override mechanism handles projects with idiosyncratic event structures that the natural mapping does not serve.

This architecture has substantial implications. Any OTel-compatible visualization tool (Grafana Tempo, Jaeger, Honeycomb, OpenObserve) can consume the unified stream and provide observability without per-project integration. Lattica's role becomes "provide the project-specific context and the interactive UI" rather than "build observability from scratch." Open-source tooling fills in the substrate; Lattica fills in the experience.

The toolkit's branching feature interacts with OTel in an interesting way. When the toolkit branches an event log (forks history at a point), the branched stream becomes a new OTel trace with a parent reference to the trunk. Counterfactual experiments become inspectable in OTel as parallel traces. This is a capability most OTel ecosystems don't natively support; the toolkit provides it as a side effect of its branching design.

## Lattica as observability hub

Lattica is a Tauri application — a Rust backend with a React frontend. The Rust backend connects to OTel data (either by running an OTel collector locally or by reading the toolkit's event log directly). The React frontend renders observability views that the backend serves.

The architecture has four layers of observability view, each suited to a different observer need.

### Layer one: the event stream view

Real-time scroll of OTel-formatted events from all connected projects. Each event shows timestamp, source project, event type, subject identifier, brief data summary. Filterable by project, event type, time window. This is the raw transactional view — what is happening right now across the ecosystem.

The event stream view is what a developer uses when something is going wrong and they need to see activity in real time. It is also what a user might glance at to see if their system is operating; the activity is its own signal that things are running.

Implementation-wise, the event stream view consumes OTel data through standard OTel exporters. It does not need direct toolkit access; it works with any OTel-compatible stream.

### Layer two: the pipeline view

Visual representation of how data flows between events within a single cognitive operation. A `cerebra search` invocation appears as a directed graph: QueryReceived → QueryPlanned → TraversalStepCompleted (six instances) → SalienceScored → ContextPacketBuilt. Each node is an event; each edge is the data carried between them. Hover or click reveals payload.

This is the most legible view for understanding what a project is doing. Event streams scroll past; pipelines are visually composable. A user looking at the pipeline view sees the cognitive operation as a whole rather than as a sequence of timestamped log lines.

Implementation requires more than OTel data alone. The graph structure (what is upstream and downstream of what) is implicit in OTel span relationships but needs to be made explicit for pipeline rendering. Lattica's backend builds the pipeline structure from OTel data by following span parent/child links and span event chains. The resulting graph is what the frontend renders.

The pipeline view is the default view in Lattica. Most observability needs are met by seeing the pipeline of recent operations; deeper inspection drops into the event stream view or the decision view.

### Layer three: the decision view

For each significant decision the system made, show the alternatives that were considered. Lattice multi-commit decisions, abstention checks, working memory eviction choices, truth tower promotion calls — each of these has a "why this and not that" structure that becomes visible when the alternatives are surfaced.

For example: "This chunk was committed to DESIGN at 0.78 confidence. CONSTRAINT also passed the threshold at 0.71, so both records were written as siblings. OBSERVATION was considered (0.43 confidence, below threshold). PRINCIPLE was considered (0.31 confidence, below threshold)."

This is the view that makes the *witness substrate* visible. The system's cognitive operations include not just what was done but what was considered and not done. The decision view exposes the not-done alongside the done, which is what training methodology consumers need.

Implementation depends on the events carrying enough structured data to reconstruct alternatives. The lattice's `LatticeShadowsRecorded` event from the dark matter substrate document does exactly this. The retrieval substrate's `RetrievalAbstained` event from Phase 4 also does this. Other event types may need enrichment to include alternatives data.

### Layer four: the pattern view

Aggregations over time. "Cerebra has abstained on 14% of context queries this week. The most common abstention reason is weak semantic with no SKU match. Tower citation rate is 0.34 — most T1 items are not getting promoted to T2."

This is the meta-cognitive view. Trends rather than instances. Patterns rather than events. The pattern view is what informs training methodology decisions, calibration tuning, and architectural review. A pattern view that shows abstention rate rising over time signals that something has shifted in the corpus or in the user's query patterns; a pattern view that shows tower citation rate falling signals that the user is treating retrieval as transactional rather than building knowledge.

Implementation requires aggregation infrastructure beyond what OTel provides natively. The witness layer concept from the Phase 6+ cognitive extensions document is the natural substrate for this. Witness projections aggregate the OTel event stream into pattern-shaped state that Lattica can query. The pattern view is essentially Lattica's UI for witness projections.

## Project-specific instrumentation

Each project in the ecosystem needs to emit OTel-formatted events for its cognitive operations. The instrumentation work is project-by-project but follows a consistent pattern.

For Cerebra specifically, the existing inspector_events table is the foundation. Each event type already emitted by Cerebra needs an OTel mapping — typically as a span with the event_type as the span name and the event's data payload as span attributes. The cerebra/inspector module gains an OTel exporter component that converts inspector events to OTel spans.

For LumaWeave, graph operations become spans. Adding a node is a span; adjusting a layout is a span; rendering a view is a span. The graph state at each moment is queryable as the trace's state at the span's end time.

For Policy Scout, eval runs become traces. Each EvalCase execution is a span; the eval suite as a whole is a trace; assertion results become span events. This gives developers visibility into which assertions are passing and failing over time.

For the discord-bot, each conversation becomes a trace. Each message is a span; tool calls within the message are child spans; LLM calls are also child spans. The conversational structure becomes visible in OTel views.

For the LLM hosting stack, each inference request is a span. Model selection, batching, response generation all become child spans. Production telemetry like token usage, latency, and error rates emerges naturally from the OTel data.

The pattern is consistent: each meaningful cognitive operation becomes a span; events within operations become span events; cross-operation relationships become span links. Once a project has its events mapped to OTel, Lattica's observability automatically extends to it.

## OpenTelemetry configuration

OTel export is configurable per-project. Three configuration concerns:

The sampling rate controls how much OTel data is emitted. In development environments, 100% sampling captures everything. In production, lower sampling rates reduce overhead. Cerebra and other cognitive projects probably want high sampling rates (the events are themselves cognitive substrate) but the LLM hosting stack might want lower sampling for performance.

The exporter destination controls where OTel data goes. The toolkit's default is to export to a local OTel collector that batches and forwards. Production deployments might export to a managed service (Honeycomb, Datadog); development might export to local Jaeger or Grafana.

The attribute filtering controls which event payload fields become OTel span attributes. Some payload data is too large to include directly (full chunk content, large JSON blobs); these should be referenced by ID rather than embedded. Some payload data is sensitive (user content, credentials) and should be filtered or hashed before export.

The configuration lives per-project, in each project's standard configuration mechanism (Cerebra's config.py, LumaWeave's equivalent). The toolkit provides defaults that work for most cases; projects override as needed.

## What Lattica's observability does not need to do

The architecture deliberately limits what Lattica builds. Several things that observability platforms typically build, Lattica should not build:

Custom event aggregation infrastructure. The toolkit's projections plus OTel's aggregation capabilities cover this. Lattica's pattern view consumes witness projections; it does not implement aggregation itself.

Custom search and query infrastructure for events. OTel-compatible backends (Tempo, Jaeger, etc.) already provide event search. Lattica's UI sits on top of these; it does not reimplement the search backend.

Custom alerting and notification infrastructure. The OTel ecosystem has mature alerting tools (Grafana Alertmanager, etc.). Lattica's role is interactive observation, not on-call paging. Users who want alerts configure them in their OTel backend of choice.

Custom data retention policies. The toolkit handles event log retention; OTel backends handle their own retention. Lattica reads from these substrates; it does not manage their lifecycles.

The discipline is: Lattica is an interactive observability experience built on standard substrates. It is not a full observability platform. The work it does not do is the work that already exists in the open-source ecosystem; the work it does do is the project-specific context and visualization that does not exist elsewhere.

## Implementation sequencing

The work is sequenced across multiple phases of the broader roadmap.

Phase one is the toolkit's basic OTel export. The Rust core's OTel integration ships as part of the toolkit's Phase 0 or Phase 1. This is foundational; nothing in the rest of the observability story works without it.

Phase two is Cerebra's OTel instrumentation. Cerebra's existing inspector module gets an OTel exporter component. This is straightforward work once the toolkit is exporting OTel; Cerebra-specific event types need their OTel mappings defined but the mapping pattern is repetitive.

Phase three is Lattica's first observability views. The event stream view comes first because it is the simplest to build (consume any OTel stream, render). The pipeline view comes next once enough Cerebra events are flowing to make pipeline rendering valuable.

Phase four extends instrumentation to other projects. LumaWeave, Policy Scout, the discord-bot, and others get their OTel mappings. The pattern is established by Cerebra's work; each subsequent project benefits from the precedent.

Phase five adds the decision view to Lattica. This requires event types across the ecosystem to carry alternatives data (the lattice's shadows, the retrieval substrate's abstention candidates, etc.). It may also require some events to be enriched with additional data that the decision view consumes.

Phase six adds the pattern view. This requires the witness layer to exist (Phase 6+ cognitive extension) and to be exposing projections that Lattica can query. The pattern view is the most ambitious of the four; it depends on capabilities that do not yet exist.

The total work is substantial but distributed across phases. No single phase carries the full implementation; each phase is bounded enough to ship without enormous risk. The architecture scales gracefully as the ecosystem grows.

## What this document is and is not

This is an infrastructure design document. It specifies the architectural shape of cross-project observability but does not implement it. Implementation depends on the toolkit being built, on each project being instrumented, and on Lattica having the UI surface to render observability views.

The document is not a complete OpenTelemetry tutorial. It assumes the reader is familiar with OTel's core concepts (traces, spans, attributes, span links) or can become familiar through standard OTel documentation. The novelty here is the integration pattern across the Lattica ecosystem, not the OTel concepts themselves.

The document does not pin down which OTel backend tools to use. Open-source options (Tempo, Jaeger, Grafana) and commercial options (Honeycomb, Datadog) are all OTel-compatible; the choice depends on factors like cost, retention needs, and visualization preferences. Lattica is agnostic to the backend choice; it consumes OTel data regardless of which tool stores it.

The architecture is opinionated about one thing: the toolkit is the substrate, OTel is the format, Lattica is the experience layer. Substitutes for any of these are possible but would require redoing the integration design. The opinionation is justified by the ecosystem's specific needs; other ecosystems might choose differently.

---

*This document depends on the event sourcing toolkit revision document for the substrate architecture and on the Phase 6+ cognitive extensions document for the witness layer that powers the pattern view. A reader new to the Lattica observability story should read those documents before this one.*
