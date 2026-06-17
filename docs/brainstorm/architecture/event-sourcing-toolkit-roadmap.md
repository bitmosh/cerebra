# Local-first event sourcing toolkit

## Roadmap and design document

---

## 1. Vision

A single-file-embeddable event sourcing library that gives any app perfect undo, time-travel debugging, branchable history, and reproducible replay — without a server, without a vendor, and without learning a paradigm shift to use it. SQLite is the substrate. The current state is always derivable from the log. The log is the truth.

One-sentence pitch: *"Like Git for application state — every change is a commit, every state is reconstructible, branches are cheap, and the whole thing fits in a single file."*

---

## 2. What event sourcing actually is

Your bank doesn't store "your balance is $487." It stores every deposit and withdrawal as an immutable record, and your balance is computed by summing them. The full transaction log is the source of truth; the balance is just a view derived from the log at any moment.

Most apps work the opposite way. They store the current state directly — "user.balance = 487" — and overwrite it on every change. The history is lost. Undo requires a separate stack. Audit requires extra logging. Reproducing a bug requires hoping the user can remember what they did.

Event sourcing flips the storage model. You store the events (the things that *happened*), and current state is computed by replaying them. From that one inversion, you get:

- **Perfect undo** — any event can be reversed by computing state without it
- **Time travel** — replay up to any timestamp to see state as it was
- **Audit log** — the event log *is* the audit log; nothing happens off the record
- **Branching** — replay events with one modification to explore alternate histories
- **Reproducibility** — bugs replay exactly given the same event sequence
- **Multiple views** — many projections can be derived from the same log
- **Schema migration without dread** — old events can be upcasted to new shapes

The cost is conceptual: developers used to CRUD have to think differently. The toolkit's job is to make that conceptual shift cheap.

---

## 3. Why local-first ES is the open gap

The landscape as of 2026:

| Library | Language | Storage | Local-first? | Viewer? | Branching? |
|---------|----------|---------|--------------|---------|------------|
| EventStoreDB | Server | Custom | No (dedicated server) | Basic web UI | No |
| Castore | TypeScript | DynamoDB/S3 | No (AWS-shaped) | No | No |
| Emmett | TypeScript | Postgres/Mongo/SQLite | Partial | No | No |
| eventually-rs | Rust | Postgres/in-memory | No (server-shaped) | No | No |
| esrs (prima) | Rust | Postgres | No | No | No |
| Axon | Java | Various | No | Commercial | No |
| EventStore (.NET) | C# | Custom | No | Yes | No |

What's missing across the field:

1. **No library treats SQLite + single-file persistence as the default** — they all assume server topology even when they support SQLite as an option.
2. **No library ships a time-travel viewer in-tree** — every team that adopts ES eventually builds one badly.
3. **No library has branchable history as a first-class concept** — branching exists in research papers and game-save systems but not in mainstream ES libs.
4. **No library is designed with agents in mind** — events are not LLM-shaped, replay isn't aware of nondeterministic LLM calls.

Each of those is a real gap. Filling all four with one cohesive library, in TypeScript, with a clean API, is what makes this a bleeding-edge offering rather than yet another ES library.

---

## 4. Core concepts and API sketch

### Concepts

- **Event** — an immutable record of something that happened. Has a type, a version, a payload, a timestamp, a content-addressed ID, and a stream ID it belongs to.
- **Stream** — an ordered sequence of events for one logical entity (e.g. one note, one user, one agent run).
- **Aggregate** — a typed entity that owns a stream. Has an initial state, a set of event reducers (event + state → new state), and a set of command handlers (command + state → events).
- **Command** — an intent to change state. Goes in; events come out (or rejection comes out).
- **Projection** — a read model derived by folding events. Can target a single aggregate, many aggregates, or the whole log.
- **Store** — the persistence layer. Provides `append`, `read`, `subscribe`, `snapshot`.
- **Snapshot** — a periodic checkpoint of an aggregate's state, so rehydration doesn't replay from the beginning every time.
- **History** — the full event log, treated as a directed graph (linear by default, branchable when forked).

### API sketch (TypeScript)

```ts
import { defineEvent, defineAggregate, SqliteStore } from '@yourname/es';

// 1. Define events with content-addressed IDs.
const NoteCreated = defineEvent('NoteCreated', 1, {
  schema: { id: 'string', text: 'string' },
});

const TextEdited = defineEvent('TextEdited', 1, {
  schema: { pos: 'number', insert: 'string', remove: 'number' },
});

// 2. Define an aggregate.
const Note = defineAggregate({
  name: 'Note',
  initial: () => ({ id: '', text: '', deleted: false }),
  reducers: {
    NoteCreated: (s, e) => ({ ...s, id: e.id, text: e.text }),
    TextEdited:  (s, e) => ({ ...s, text: applyEdit(s.text, e) }),
  },
  commands: {
    create: (s, c: { text: string }) =>
      [{ type: 'NoteCreated', id: ulid(), text: c.text }],
    edit: (s, c: { pos: number; insert: string; remove: number }) =>
      [{ type: 'TextEdited', ...c }],
  },
});

// 3. Open a store and start using it.
const store = new SqliteStore('./notes.db');

const note = await store.aggregate(Note, 'note_abc');
await note.execute('create', { text: 'Hello world' });
await note.execute('edit',   { pos: 5, insert: ' brave', remove: 0 });

console.log(note.state.text); // "Hello brave world"

// 4. Time travel.
const past = await store.aggregateAt(Note, 'note_abc', { atVersion: 1 });
console.log(past.state.text); // "Hello world"

// 5. Branch.
const branch = await store.branchFrom('note_abc', { atVersion: 1, name: 'alt' });
await branch.execute('edit', { pos: 5, insert: ' bold', remove: 0 });
console.log(branch.state.text);  // "Hello bold world"  (in branch 'alt')
console.log(note.state.text);    // "Hello brave world" (in main)

// 6. Subscribe — projections rebuild reactively.
const unsub = store.subscribe(Note, 'note_abc', (state, event) => {
  ui.render(state);
});
```

### Design priorities, in order

1. **Type safety end-to-end** — commands, events, projections all typed; no string-typed event handlers.
2. **Single dependency to install, one line to start** — `new SqliteStore('./app.db')` and you're sourcing events.
3. **Pluggable storage backend** — interface so SQLite, memory, IndexedDB, and (eventually) network stores all conform.
4. **Zero-config snapshots** — the library decides when to snapshot; user can override.
5. **Branches are equal citizens** — `main` is just the default branch name, not a special case.

---

## 5. Use cases — concrete scenarios

### 5.1 Personal note-taking with recoverable history

User edits a note over weeks. They delete a paragraph. Months later they want it back. In a CRUD app it's gone. With this toolkit:

```ts
const note = await store.aggregate(Note, noteId);
const yesterday = await store.aggregateAt(Note, noteId, {
  at: Date.now() - 86400000
});
diff(yesterday.state.text, note.state.text);
```

The time-travel viewer in phase 1 makes this clickable rather than code-driven. Users scrub a timeline; the document state updates live. Branches let them recover the deleted paragraph into a new note without modifying the original.

### 5.2 Agent reasoning trace and counterfactual replay

An agent runs with 50 tool calls and gives a wrong answer. Each LLM call, tool call, observation is an event in a stream named for that run:

```ts
await runStream.execute('llm_call', { prompt, response, tokens });
await runStream.execute('tool_call', { name: 'search', args, result });
await runStream.execute('llm_call', { prompt, response, tokens });
```

To debug:

```ts
// Replay deterministically (tool outputs are stored, so no re-calls)
const original = await store.replay(Run, runId);

// Branch from event 23 and rewrite event 24
const branch = await store.branchFrom(runId, { atVersion: 23 });
await branch.append({
  type: 'llm_call',
  prompt: corrected_prompt,
  response: simulated_response,
});

// Run forward from there
const counterfactual = await store.replay(Run, branch.id);
```

This is *exactly* the substrate lumaweave needs for static-vs-live dogfooding. The static run is the original stream; the live run is a branch with edits.

### 5.3 Bonsai idea evolution as event log

Every mutation, every fitness evaluation, every cull is an event:

```ts
type IdeaEvent =
  | { type: 'Mutated';  parent: id, child: id, op: string }
  | { type: 'Scored';   id: id, score: number, metric: string }
  | { type: 'Culled';   id: id, reason: string };
```

Genealogy is automatic — to find an idea's ancestry, walk parent edges in the `Mutated` events. The current population is a projection. Bonsai can branch at any historical point to run a counterfactual evolution (what if we had selected differently at generation 200?).

### 5.4 Personal finance with audit-grade history

Every transaction is an event; balance is a projection; categories are projections; monthly summaries are projections. Time-travel answers "what was my balance on March 12?" without any explicit history table. Every projection can be rebuilt from the log if its schema changes — no migration scripts needed.

### 5.5 Game save / replay system

Every player action is an event. "Save anywhere" is free — every state is reconstructible. Replay your run by streaming the events back at any speed. Branch from any moment to try a different choice. This is what speedrun tools want to be.

---

## 6. Architecture

```
                            +---------------------+
              commands ---> |     Aggregate       | ---> events
                            +---------------------+
                                      |
                                      v
                            +---------------------+
                            |       Store         |
                            |  (SQLite default)   |
                            +---------------------+
                              |       |        |
              +---------------+       |        +---------------+
              v                       v                        v
     +-----------------+    +-----------------+      +-----------------+
     |   Projections   |    |    Snapshots    |      |   Subscribers   |
     |  (read models)  |    |  (rehydration)  |      |  (reactive UI)  |
     +-----------------+    +-----------------+      +-----------------+
              |
              v
     +-----------------+
     |   Time-travel   |
     |     viewer      |
     +-----------------+
```

The hot path is: command in → aggregate validates → events appended atomically → projections fold → subscribers fire. Snapshots run on a separate cadence (every N events per stream by default). The time-travel viewer is a separate consumer that reads the log directly.

### Storage layout (SQLite)

```sql
CREATE TABLE events (
  id           BLOB PRIMARY KEY,    -- content-addressed (blake3)
  stream_id    TEXT NOT NULL,
  branch       TEXT NOT NULL DEFAULT 'main',
  version      INTEGER NOT NULL,    -- per-stream-per-branch ordinal
  type         TEXT NOT NULL,
  type_version INTEGER NOT NULL,
  payload      BLOB NOT NULL,       -- msgpack
  timestamp    INTEGER NOT NULL,    -- ms epoch
  causation_id BLOB,                -- for forks
  UNIQUE (stream_id, branch, version)
);
CREATE INDEX idx_stream_branch_version ON events (stream_id, branch, version);
CREATE INDEX idx_timestamp ON events (timestamp);

CREATE TABLE snapshots (
  stream_id  TEXT NOT NULL,
  branch     TEXT NOT NULL,
  version    INTEGER NOT NULL,
  state      BLOB NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (stream_id, branch, version)
);

CREATE TABLE branches (
  id              TEXT PRIMARY KEY,
  parent_id       TEXT REFERENCES branches(id),
  parent_version  INTEGER,
  created_at      INTEGER NOT NULL,
  metadata        BLOB
);
```

Three tables, no more. Content-addressed IDs (blake3 of `type + payload + causation_id`) give us free dedup and verification.

---

## 7. Phase-by-phase roadmap

### Phase 0 — week 1: Minimum viable substrate

**Ship goal:** a working library you can `npm install` on Friday, with a README, a tutorial, and 80% test coverage of the core path. No viewer, no branching, no sync. Just rock-solid linear ES.

| Day | Deliverable |
|-----|-------------|
| Mon | Project skeleton, types (Event, Aggregate, Projection, Store), interfaces locked. Memory store working end-to-end. |
| Tue | SQLite store with the three-table schema. WAL mode, prepared statements, transactional appends. Stream rehydration. |
| Wed | Snapshots (auto-trigger every N events), projections (folder API), basic CLI inspector (`es log <stream-id>`). |
| Thu | Tests — unit, property-based for the reducer/folder invariants, integration scenarios. Bench rehydration cost. |
| Fri | README + tutorial + one runnable example app. Tag v0.1.0, publish to npm under a scoped name, post about it. |

**Definition of done for v0.1.0:**

- `defineEvent`, `defineAggregate`, `defineProjection` all type-safe
- `MemoryStore` and `SqliteStore` both implement the same `Store` interface
- Append is atomic (event + version increment in one transaction)
- Rehydration uses snapshots when available, replays from snapshot to head
- CLI: `es log`, `es head`, `es replay <stream> --until <version>`
- One end-to-end example (the note-taking app from section 5.1)
- README explains ES in 5 paragraphs and shows the API in 30 lines

### Phase 1 — weeks 2 and 3: The "wow" features

This is where the library gets *interesting* relative to the competition. Each week ships independently.

**Week 2: Time-travel viewer**
A small HTML/canvas UI that connects to a store and renders the event log as a scrubbable timeline. Click any event, see the state as of that event. Diff between two events. Filter by stream, by type, by time range. Ship as `@yourname/es-viewer`, embed in user apps with one line.

The viewer is the demo. It's what makes people *get* the value in the first 30 seconds. Building it second (not first) means the library is solid before the eye candy lands.

**Week 3: Branchable history + reactive subscriptions + event versioning**
- `store.branchFrom(streamId, { atVersion, name })` creates a parallel history. Branches share the trunk events up to the fork point.
- `store.subscribe(...)` registers a callback that fires on every relevant append. Frameworks (React, Vue, Solid) hook into this in phase 3.
- Event versioning + upcasters: when you change an event's schema, you register an upcaster `(oldEvent) => newEvent` that runs at read time. No data migration needed.

### Phase 2 — weeks 4 to 6: Bleeding edge

**Week 4: CRDT sync via Loro**
Optional add-on package. Your event log syncs across devices using Loro CRDTs as the transport. Conflicts (same stream, divergent branches) are resolved by treating them as branches and surfacing the choice to the application. Local-first multi-device, no central server.

**Week 5: Agent trace adapter**
A specialization layer for recording agent runs. Standard event types: `llm_call`, `tool_call`, `tool_result`, `reasoning_step`. Captures tool outputs so replay is deterministic. Exports to OpenTelemetry GenAI span format. Branches become natural counterfactual experiments.

**Week 6: Schema migration tooling + projection caching**
- Migration helpers when an upcaster isn't enough (rare; covers schema splits/merges).
- Projections can be marked cacheable; the library memoizes them keyed on `(stream_id, branch, version)` so reads are O(1) after the first.

### Phase 3 — week 7 onwards: Ecosystem

The library is feature-complete. This phase is adoption work.

- Framework hooks: `useAggregate`, `useProjection` for React/Vue/Solid
- OpenTelemetry exporter (events become spans)
- A2A protocol adapter (each A2A message is an event)
- Integration with your other modules:
  - `#14 semantic file watcher` → fire events on meaningful change
  - `#15 reversible FSM` → use the event log as its backing store
- Docs site, blog posts, example apps (note app, todo app, agent runner)

---

## 8. Differentiators — what makes this distinct

| Feature | Castore | Emmett | eventually-rs | This toolkit |
|---------|---------|--------|---------------|--------------|
| TypeScript-native | yes | yes | no | yes |
| SQLite single-file default | no | optional | no | yes (primary) |
| Embeddable (no server) | partial | partial | no | yes |
| Time-travel viewer in-tree | no | no | no | yes |
| Branchable history | no | no | no | yes |
| Content-addressed events | no | no | no | yes |
| Local-first sync (CRDT) | no | no | no | yes (phase 2) |
| Agent-trace adapter | no | no | no | yes (phase 2) |
| Reactive subscriptions | partial | yes | partial | yes |

The combination is the moat. Any individual feature exists somewhere; nothing combines all of them.

---

## 9. Traps to design around from day one

These are the design decisions that look small at v0.1.0 but become expensive later if you get them wrong. Lock them in week 1.

1. **Projection runner isolation.** A projection that throws must not corrupt the writer. Run projections in a separate microtask queue (Node) or thread (Rust) from day one — even if the v0.1.0 only has in-process projections, the *interface* must allow them to fail independently.

2. **Event IDs are content-addressed from day one.** Even if you don't use the dedup property in v0.1.0, switching from auto-incrementing IDs to content-addressed later is a migration nightmare. Hash `(type + payload + causation_id)` with blake3 and store the hash as the primary key.

3. **Don't let users access events by integer offset.** Always by stream + version + branch, never by a global integer. Global offsets break branching and break sync.

4. **Reducers must be pure and synchronous.** No promises, no I/O, no external state. The library can enforce this with a type-level constraint and a runtime assertion. The moment a reducer makes a network call, your replay determinism is gone.

5. **Snapshots are an optimization, not part of the model.** State must be derivable from events alone. If a snapshot is corrupt or absent, replay from zero must produce the identical state. Test this property explicitly.

6. **Branches share storage, not copies.** A branch is a pointer (`parent_id`, `parent_version`) plus its own appended events. Don't copy trunk events into branches — you'll explode storage and lose the relationship.

7. **Version your event types from event #1.** Even if v0.1.0 only supports type version 1, every event carries `type_version` in its envelope. Day-one upcasters don't have to do anything, but the path is there.

8. **Don't conflate stream ID with aggregate ID.** A stream is the unit of ordering; an aggregate is the unit of identity. In simple apps they're 1:1, but in advanced cases (e.g. one stream for all events across a tenant) they diverge. Keep them separate in the type system.

---

## 10. Open design questions to settle before Monday

These are decisions I'd want to make with you before any code is written. None are blockers, but locking them in saves rework.

1. **Language: TypeScript-first or Rust-first?** TS-first ships faster, integrates with web and Node. Rust-first gives a single binary and the easiest path to embedding in non-TS apps. My recommendation: TS-first for v0.1.0, Rust port in phase 2 if there's demand.

2. **Serialization format: JSON or msgpack?** JSON is debuggable and human-readable; msgpack is ~30% smaller and faster. Recommendation: msgpack on disk, JSON view in the CLI inspector.

3. **Async API or sync API?** Even with SQLite the operations are I/O. TS-first means async. Recommendation: async public API, sync internals where SQLite permits.

4. **Snapshot strategy: count-based, time-based, or hybrid?** Recommendation: count-based by default (every 100 events per stream), configurable per-aggregate.

5. **License: MIT or Apache 2.0?** Recommendation: MIT for the core, Apache 2.0 for adapter packages so contributions are easier.

6. **Distribution: monorepo or polyrepo?** Recommendation: monorepo (pnpm workspaces) with separate publish targets. `core`, `sqlite`, `viewer`, `react` as four packages from day one.

---

## 11. Module structure

```
event-sourcing-toolkit/
├── packages/
│   ├── core/                # zero-dep types and interfaces
│   │   ├── src/
│   │   │   ├── event.ts
│   │   │   ├── aggregate.ts
│   │   │   ├── projection.ts
│   │   │   ├── store.ts
│   │   │   ├── upcaster.ts
│   │   │   ├── id.ts        # content-addressed IDs (blake3)
│   │   │   └── index.ts
│   │   └── tests/
│   ├── store-memory/        # in-memory store for tests
│   ├── store-sqlite/        # the default store
│   ├── viewer/              # phase 1: time-travel HTML viewer
│   ├── sync-loro/           # phase 2: optional CRDT sync
│   ├── agent-trace/         # phase 2: agent-run specialization
│   ├── react/               # phase 3: useAggregate / useProjection
│   ├── otel/                # phase 3: OpenTelemetry exporter
│   └── cli/                 # the inspector
├── examples/
│   ├── notes/
│   ├── agent-runner/
│   └── bonsai-evolution/
├── docs/
├── benchmarks/
└── README.md
```

Each package publishes independently. Core has zero dependencies. The store packages depend only on core. The viewer is the only package that ships HTML/JS to the browser.

---

## 12. What success looks like

- **v0.1.0 published by Friday** — basic ES works, README is clear, one example runs.
- **One real user in two weeks** — either your own use in lumaweave/cerebra/bonsai, or someone you've shown the demo to.
- **Time-travel viewer demo gets shared** at end of week 2 — that's the moment the project becomes legible to people who don't know ES.
- **Branching feature lands at end of week 3** — that's the moment you have something the field doesn't have.
- **By week 6**, the toolkit is the persistence story for at least one of your other modules.
- **By week 12**, it's adopted by someone outside your own project surface.

The path is real. The work is mostly idiomatic TypeScript. The wins compound because every later module gets reproducibility for free.
