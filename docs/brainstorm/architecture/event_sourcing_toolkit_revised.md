# Event Sourcing Toolkit — Architecture Revision

*Design document — drafted 2026-06-12. Supersedes the language and distribution sections of the original event-sourcing-toolkit-roadmap.md. Preserves the conceptual model, API design, and use cases from the original. Reframes the implementation as Rust core with Python and TypeScript adapters rather than TypeScript-first with Rust port deferred.*

---

## Why this revision exists

The original toolkit roadmap was drafted as a TypeScript-first project with a Rust port noted as a possible Phase 2 addition. That framing was reasonable in isolation — the developer most often works in TypeScript, the toolkit's primary near-term consumers are JS/Node-shaped, and TypeScript-first ships faster. But the framing did not account for the broader ecosystem the toolkit is being built within.

The Lattica suite includes projects in Python (Cerebra, ai-stack, discord-bot, Policy Scout, potentially Bons.ai, potentially Rhyzome) and projects in TypeScript or Rust-with-TypeScript (Lattica itself as a Tauri app, LumaWeave). The toolkit is intended to be infrastructure these projects depend on. Infrastructure consumed by multiple projects in multiple languages benefits from being implemented in a *single-source-of-truth* core that all language ecosystems can call into, not as a per-language implementation that needs to be maintained in parallel.

The revision proposes implementing the core in Rust and exposing it through Python and TypeScript adapters. The conceptual model, API surface, storage layout, and use cases from the original roadmap remain valid. What changes is the language of the core implementation and the distribution model.

## The argument for Rust as core

Three properties of the toolkit's domain make Rust a substantively better fit than TypeScript for the core.

The toolkit's hot path is event appending and projection folding against SQLite. These operations need to be atomic, predictable in performance, and free of garbage-collection pauses that could interleave with concurrent reads. Rust's ownership model gives compile-time guarantees about these properties that TypeScript's runtime semantics cannot match. A buggy projection in a TypeScript implementation could allocate unbounded memory, cause GC pauses that delay event appends, or violate atomicity through unexpected await points. A Rust implementation closes off these failure modes structurally.

The toolkit will be embedded in long-running processes that hold the event log open for the lifetime of the consumer process. Memory leaks at that scale matter. Rust's ownership and borrow-checking make memory leaks substantially harder to introduce; the typical patterns that produce leaks in TypeScript (closures retaining references, unbounded subscriber arrays, projection state that grows without bound) are caught at compile time in Rust or produce visible warnings.

The toolkit is intended to be consumed from multiple language ecosystems. A Rust implementation can be exposed cleanly to other languages through well-established FFI patterns. PyO3 for Python, napi-rs or wasm for TypeScript, cbindgen for C-compatible bindings. The same compiled core serves all consumers. A TypeScript implementation, by contrast, cannot be cleanly consumed from Python without either an HTTP server (operational overhead, latency), a CLI subprocess (slow, no streaming), or a Node.js bridge (deployment complexity). The mismatch becomes visible when a Python project wants the toolkit's projections in the same memory space as its application logic, which is the normal case for performance-sensitive consumers.

These three properties together — predictability in the hot path, leak resistance for long-running embedding, clean multi-language consumption — make Rust the right choice for the core implementation. None of them are exotic Rust capabilities; they are standard properties of Rust code written competently. The decision is not adopting Rust for novelty but recognizing that the toolkit's structural requirements happen to match Rust's structural strengths.

## The adapter architecture

The Rust core implements the conceptual model from the original roadmap: events, streams, aggregates, commands, projections, snapshots, branches. The core's API is exposed through three primary interfaces.

**A native Rust API** for Rust consumers. This is the lowest-overhead path. Projects written in Rust link the toolkit as a crate dependency and call its functions directly. Use cases include Lattica's Tauri backend (which is Rust) and any future Rust-based projects in the Lattica suite.

**A Python adapter** built with PyO3. Python consumers install the toolkit as a PyPI package and use a Pythonic API that wraps the Rust core. The Python adapter handles serialization across the FFI boundary (msgpack for performance, with optional JSON for debugging) and provides idiomatic Python ergonomics (context managers for transactions, generators for event streams, dataclasses for event types). Cerebra, the LLM hosting stack, the discord-bot, and Policy Scout are the near-term Python consumers.

**A TypeScript adapter** built with napi-rs. TypeScript consumers install the toolkit as an npm package and use an API consistent with the original roadmap's TypeScript design. The TypeScript adapter handles the same serialization layer as Python but exposes a JS-idiomatic API. LumaWeave, Lattica's React frontend, and any future TypeScript projects consume through this adapter.

The wire format between adapters and the Rust core is consistent. An event written through the Python adapter is byte-identical to an event written through the TypeScript adapter (modulo language-specific representations of the payload). The event log is portable across all consumers regardless of which adapter produced its entries.

## Distribution and deployment modes

The toolkit ships in three deployment modes, each suited to different use cases. All three modes use the same Rust core; what differs is the topology of who reads and writes the event log.

**Embedded mode** is the simplest deployment. A consuming project links the toolkit (Rust crate, Python package, or npm package) as a library dependency. The project owns the event log file directly. No daemon, no IPC, no coordination with other processes. This is the default mode and the easiest to adopt.

A consuming project that wants event sourcing for its own internal state uses embedded mode. Cerebra's own use of event sourcing for its inspector substrate would be embedded mode. LumaWeave's use for its graph operations would be embedded mode. Each project gets its own event log; the logs are independent unless explicitly shared.

**Shared-file mode** extends embedded mode by allowing multiple processes to open the same event log file. SQLite's WAL mode supports concurrent readers safely; the Rust core adds proper locking for concurrent writers. Two projects can append to the same event log without coordination beyond the file system path.

A consuming pattern that wants cross-project event visibility uses shared-file mode. Cerebra writes events to a log; Lattica reads from the same log to render observability views. Both projects link the toolkit; both open the same file; the Rust core handles concurrent access correctly. No daemon, no API surface, just a shared file.

**Daemon mode** is the heaviest deployment but the most flexible. The Rust core runs as a background process holding the event log; consumers connect via Unix domain sockets and submit events or read projections through an IPC protocol. The daemon handles concurrency, lifecycle, and isolation between consumers.

A production deployment that hosts multiple projects' event logs together uses daemon mode. Lattica's eventual production surface might be a daemon that owns event logs for Cerebra, LumaWeave, Policy Scout, and the discord bot simultaneously. Each project connects to the daemon rather than owning event log files directly. The daemon centralizes lifecycle management, backup, and access control.

The three modes are not mutually exclusive within a single ecosystem. A development environment might use embedded mode for fast iteration; the same code in production might be reconfigured to use shared-file mode for cross-project visibility or daemon mode for centralized management. The Rust core abstracts the mode choice; consuming code is largely agnostic to which mode is active.

## Integration with Cerebra specifically

Cerebra's inspector_events table is functionally an event log. The schema is not identical to what the toolkit prescribes, but the conceptual model is the same: immutable append-only records of cognitive events, queryable for audit and projection. The toolkit can integrate with Cerebra in two ways.

The minimal integration treats Cerebra's inspector_events as a separate event log that the toolkit reads from. The toolkit's projection layer subscribes to Cerebra's events without owning them. Cerebra keeps its current schema; the toolkit adapts. This is straightforward but limits the toolkit's value — Cerebra cannot use the toolkit's branching, snapshotting, or replay features against its own events without further integration.

The deeper integration migrates Cerebra's inspector_events to the toolkit's schema. The Rust core owns the event log file; Cerebra's Python code uses the Python adapter to write events. This requires schema migration (Cerebra's current event_id format would need to migrate to content-addressed IDs, the stream_id column would need to be populated, etc.) but unlocks the toolkit's full feature set for Cerebra.

The deep integration is the right long-term target but requires care. Cerebra's existing event consumers (the inspector log, the search/context/etc. CLI commands that emit events) all need to be updated to use the new write path. The migration is forward-only; the existing event records need to be preserved or migrated cleanly.

Practical sequencing: deep integration of Cerebra with the toolkit waits until the toolkit is built and stable. The minimal integration (toolkit reads Cerebra's existing events without owning them) is the first step. When the toolkit's core is solid, Cerebra's events can migrate as a planned change rather than as an experimental dependency.

## OpenTelemetry as natural Phase 3 work

The toolkit roadmap's Phase 3 mentions OpenTelemetry as an exporter capability. With the Rust core in place, this becomes a substantially more powerful capability than the original roadmap envisioned.

Rust has mature OpenTelemetry support through the opentelemetry-rust crate. The toolkit's Rust core can export events as OTel spans directly, with the span hierarchy mapping naturally onto the toolkit's stream and aggregate structure. A stream becomes a parent span; events within the stream become child spans; subscriptions and projections become processing relationships visible in span links.

The cross-project implication is substantial. If Cerebra, LumaWeave, Policy Scout, and the discord-bot all use the toolkit and all enable OTel export, their events accumulate in a unified observability stream. Any standard OTel-compatible tool (Grafana Tempo, Jaeger, Honeycomb) can consume the stream and provide visualization, alerting, and analysis without per-project integration work.

Lattica's observability layer becomes a thin consumer of the OTel stream rather than a custom-built event aggregator. The work of "show me what's happening across all projects" is solved by the OTel ecosystem; Lattica's role becomes "provide the project-specific context and the interactive UI" on top of OTel data. This is substantially less work than building a custom observability layer from scratch.

OTel export should be off-by-default for performance, opt-in via configuration. Embedded mode might have it off; daemon mode might have it on. The flexibility is part of why having it baked into the core rather than added as a per-adapter feature matters.

## What changes from the original roadmap

The original roadmap remains valid for its conceptual model, API design patterns, storage schema, and use cases. The specific changes from the original document:

The language framing changes from "TypeScript-first, Rust port in Phase 2" to "Rust core, Python and TypeScript adapters from day one." This is the primary revision.

The distribution model changes from a single npm package to three publishing targets: crates.io for the Rust crate, PyPI for the Python adapter, npm for the TypeScript adapter. The repository structure becomes a monorepo with separate publish targets, similar to the original roadmap's TypeScript-internal monorepo but extended across language ecosystems.

The phase-by-phase timeline changes. The original Phase 0 (week 1) would now produce a working Rust core with minimal Python and TypeScript adapter functionality. The original Phase 1 (weeks 2-3, wow features) becomes Phase 1 of the Rust core (branching, time-travel viewer, event versioning), with the adapters trailing slightly behind as they expose the new features. The total timeline extends modestly — perhaps an extra two to three weeks beyond the original twelve-week target — to account for FFI work and the additional ecosystem testing.

The agent trace adapter from the original Phase 2 becomes specifically a Python adapter feature, since most agent runners are written in Python. The Rust core exposes the agent-relevant primitives; the Python adapter provides idiomatic agent-tracing helpers.

The CRDT sync feature from the original Phase 2 (Loro CRDT integration) remains valid but moves into the Rust core. Loro has Rust bindings, so this is actually easier in the Rust implementation than the TypeScript one.

The framework hooks from the original Phase 3 (useAggregate, useProjection for React/Vue/Solid) remain TypeScript adapter features. Adding equivalent helpers for Python frameworks (Django, FastAPI) becomes natural Python adapter work in the same Phase 3.

## What stays the same

The conceptual model is unchanged. Events, streams, aggregates, commands, projections, snapshots, and branches remain the core abstractions. The original roadmap's argument for why these abstractions are right is independent of the implementation language.

The API surface is unchanged in spirit. The original roadmap's TypeScript API examples (defineEvent, defineAggregate, store.subscribe, etc.) remain valid as TypeScript adapter API. The Python adapter's API will be analogous in spirit but Pythonic in idiom (decorators or class-based definitions instead of object literals, async generators instead of subscription callbacks where Python convention favors them).

The storage layout is unchanged. The original roadmap's three-table SQLite schema (events, snapshots, branches) remains correct. The Rust core implements this schema; the adapters never touch SQLite directly.

The differentiators identified in the original roadmap remain valid. Single-file embeddable, time-travel viewer in-tree, branchable history, content-addressed events, local-first sync, agent-trace adapter, reactive subscriptions. The combination is still the moat. The Rust core does not change which features differentiate the toolkit; it changes how those features are delivered to consumers.

The day-one design traps from the original roadmap remain critical. Projection runner isolation, content-addressed event IDs, no-integer-offset access to events, pure-synchronous reducers, snapshots as optimization rather than model, branches share storage, version event types from event one, separate stream ID from aggregate ID. The Rust core's compile-time guarantees make some of these traps easier to avoid, but the design discipline remains the same.

The success criteria from the original roadmap remain valid. One real user in two weeks. Time-travel viewer demo shareable at end of week two. Branching feature lands at end of week three. By week six, the toolkit is the persistence story for at least one consuming project. By week twelve, adoption by someone outside the originating ecosystem.

The week-twelve target may extend by two to three weeks given the additional ecosystem work, but the structural targets are unchanged.

## Open questions

The choice of FFI library for the Python adapter is between PyO3 (the standard, well-supported, mature) and abi3-based alternatives that produce Python-version-portable binaries. PyO3 is recommended; abi3 is a consideration if Python-version portability becomes important. Decision deferred to implementation.

The choice of FFI library for the TypeScript adapter is between napi-rs (native bindings, fast, Node-only), wasm (cross-platform including browser, slightly slower), and neon (older but stable). Recommendation: napi-rs for the npm package, with wasm as an optional secondary target for browser-side consumers. Decision deferred to implementation.

The repository structure question: monorepo with all three adapters or separate repositories for each? Recommendation: monorepo (similar to the original roadmap's plan) but with clear publishing boundaries. A single source repository is easier to keep consistent; separate publish targets prevent consumers from being forced to install adapters they don't need. Decision can be reviewed at implementation time.

The OpenTelemetry export semantics: which events become spans, which become events on spans, which become attributes? The natural mapping is streams as parent spans, events as child spans, payloads as attributes. But this is opinionated and consumers may want different mappings. Recommendation: ship the natural mapping as default, allow customization via configuration. Decision deferred to Phase 3.

The naming question: the original roadmap used `@yourname/es` as the npm scope placeholder. The actual naming for the published packages needs to be decided. Recommendation: lattica-es-core (Rust crate), lattica-es (Python and TypeScript packages, since they share most of the public API surface). The lattica- prefix signals the ecosystem; the suffix differentiates the core from the adapters. Decision can be made at first publish.

## What this revision is and is not

This is a design revision, not a new design from scratch. The original roadmap's content remains the foundation; this document specifies what changes. A reader implementing the toolkit should read the original roadmap and this revision together.

The revision is not an architecture specification. The Rust core's exact module structure, the adapter's exact API shapes, the FFI binding details — all of these are implementation decisions made during the build, not pre-specified in this document.

The revision does not commit to a specific timeline. The original roadmap's twelve-week target was reasonable for a TypeScript-first implementation; the revised approach likely extends to fifteen to eighteen weeks given the additional ecosystem work, but the actual timeline depends on factors not yet known (developer focus, FFI complexity that surfaces during implementation, ecosystem testing requirements).

The revision proposes the architectural shape that fits the Lattica ecosystem's actual needs. The original roadmap was written without the full ecosystem context in view; this revision incorporates that context. Future revisions may further refine the architecture as the ecosystem evolves.

---

*This document supersedes the language, distribution, and FFI sections of event-sourcing-toolkit-roadmap.md. Other sections of the original roadmap remain authoritative. A reader new to the toolkit should read the original document first for conceptual grounding, then this revision for the implementation framing.*
