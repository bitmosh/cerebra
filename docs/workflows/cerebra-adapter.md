# Cerebra as a LumaWeave Source Adapter

**Status:** design document — no code exists yet  
**Scope:** cross-project; covers what Cerebra must emit and what LumaWeave must add  
**Last updated:** 2026-06-05

---

## §1 — What this is

LumaWeave source adapters translate external data into a normalized `LumaWeaveNodeDraft[]` / `LumaWeaveEdgeDraft[]` graph that Sigma renders. This document describes what a `cerebra-vault` adapter would need to be: the graph shape it would produce, the export artifact Cerebra must generate, the registry entry LumaWeave needs, the update model, and the full lifecycle from `candidate` to `active`.

Nothing here requires changes to either codebase today. The intent is to have a precise design ready before implementation begins.

---

## §2 — Cerebra as a source: what it has and what to expose

Cerebra's SQLite vault contains five entity layers:

```
sources → documents → chunks → memory_records ← sku_assignments
```

| Layer | What it is | Expose as graph node? |
|---|---|---|
| **sources** | A file on disk: canonical_path, content_hash, detected_type, lifecycle_state | Yes — spine node |
| **documents** | Parsed representation of a source: document_type, title, normalization_confidence | No — too intermediate |
| **chunks** | Section-level text slices: heading_path, depth, content, token_estimate | No — too granular |
| **memory_records** | The consumable knowledge unit, carries sku_address and lifecycle | Yes — leaf node |
| **sku_assignments** | Classifier output: all 10 SKU digits, raw scores, d1_confidence | Fold into record node's `raw` bag |

**Why skip documents and chunks?** Exposing all five layers would produce five times the nodes with only structural edges between them — a dense, unreadable hierarchy with no semantic signal. The meaningful graph is a two-tier structure: the files that hold knowledge (sources) and the classified knowledge units extracted from them (memory_records with SKU addresses). Documents and chunks are pipeline internals, not knowledge objects.

**Why skip stale records?** Cerebra's lifecycle model is explicit: `lifecycle_state = 'stale'` means the content was superseded by a re-ingest. Only `active` records should appear in the graph. Stale nodes would represent ghost knowledge the system has already discarded.

---

## §3 — The graph shape

### 3.1 Node types and visual treatment

**Source nodes (`type: "spine"`)** — one per active source file.

| Property | Value |
|---|---|
| `id` | `source:{source_id}` |
| `label` | filename (basename of canonical_path) |
| `fullLabel` | canonical_path |
| `type` | `"spine"` |
| `cluster` | detected_type → cluster (see mapping below) |
| `status` | lifecycle_state (`"active"` or `"stale"`) |
| `tags` | `["source", detected_type]` |
| `size` | sum of token_estimates across all active records for this source (scaled: `min(24, max(10, total_tokens / 500))`) |
| `path` | canonical_path |

detected_type → cluster mapping:
- `markdown` → `slate`
- `code` → `gray`
- `graph` → `teal`
- any other → `azure`

**Memory record nodes (`type: "memory_record"`)** — one per active memory_record with a completed sku_assignment.

| Property | Value |
|---|---|
| `id` | `record:{record_id}` |
| `label` | heading_path if non-empty, else document title, else `record_{record_id[:8]}` |
| `fullLabel` | `{source_basename} › {heading_path}` |
| `type` | `"memory_record"` |
| `cluster` | D1 quadrant → cluster (see mapping below) |
| `status` | lifecycle_state |
| `tags` | `[d1_category_name, d9_modality_name, "q{quadrant}"]` |
| `size` | token_estimate scaled: `min(12, max(4, token_estimate / 100))` |
| `path` | canonical_path of owning source |
| `raw.sku_address` | full SKU string, e.g. `"400000.03.00"` |
| `raw.d1` | integer 0–15 |
| `raw.d1_category` | e.g. `"TECHNIQUE"` |
| `raw.d1_confidence` | float 0–1 |
| `raw.d9_modality` | e.g. `"TEXT"` |
| `raw.d10_provenance` | e.g. `"OBSERVED"` |
| `raw.quadrant` | integer 0–3 |
| `raw.quadrant_name` | `"Empirical"` / `"Generative"` / `"Normative"` / `"Relational"` |
| `raw.detected_type` | inherited from owning source |
| `raw.dimFactor` | `0.7` for records with `d1_confidence < 0.5`; `1.0` otherwise |

D1 quadrant → cluster color:
- Quadrant 0 (Empirical: OBSERVATION, PATTERN, MECHANISM, PHENOMENON) → `azure`
- Quadrant 1 (Generative: TECHNIQUE, DESIGN, CREATION, TOOL) → `gold`
- Quadrant 2 (Normative: PRINCIPLE, JUDGMENT, GOAL, CONSTRAINT) → `purple`
- Quadrant 3 (Relational: EVENT, AGENT, CONTEXT, RELATION) → `teal`

Records without a completed sku_assignment are omitted entirely from the graph. They represent unclassified ingestions — not yet knowledge.

### 3.2 Edge types, weights, and colors

| Edge type | Meaning | Weight | Color | Bidirectional |
|---|---|---|---|---|
| `contains` | source spine → its memory records | 0.4 | `rgba(107,114,128,0.35)` (slate) | false |
| `describes` | record → other records in same document, by chunk adjacency | 0.65 | `rgba(79,163,224,0.4)` (azure) | false |
| `sku-proximity` | records sharing the same D1 category | `min(0.5, shared_d1_count / 20)` | `rgba(100,217,164,0.3)` (green) | true |
| `sku-exact` | records with identical sku_address | 0.9 | `rgba(224,168,79,0.55)` (gold) | true |

**Edge ID format:**
- `contains`: `edge-{source_id}-{record_id}-contains`
- `describes`: `edge-{record_id_a}-{record_id_b}-describes`
- `sku-proximity`: `edge-{record_id_a}-{record_id_b}-sku-proximity`
- `sku-exact`: `edge-{record_id_a}-{record_id_b}-sku-exact`

**Cap on sku-proximity edges**: max 5 per record node (highest-weight kept), matching LumaWeave's tag-overlap cap. Without this, a vault with 200 records all classified as `TECHNIQUE` would produce ~20,000 edges and an unreadable graph.

**Why no cross-document wikilink edges?** Cerebra does not yet parse wikilinks or cross-document references in chunk content — that's a Phase 3+ concern. When that data exists, a `wiki-link` or `explicit-reference` edge type could be added at the same weight (0.7 / 1.0) as LumaWeave's self-graph uses. The adapter schema should be extended at that point, not pre-populated with phantom edges.

---

## §4 — The export artifact: `cerebra-graph.json`

### 4.1 Why a JSON file, not direct SQLite access

LumaWeave is a TypeScript/Tauri app. Reading a SQLite binary file from the TS layer requires either a WASM SQLite library (new dep, needs approval) or a Rust command that queries and serializes — significant complexity. The self-graph adapter, the only shipped adapter, uses a pre-generated JSON fixture. Cerebra should follow the same pattern: produce a `cerebra-graph.json` artifact, which LumaWeave reads exactly as it reads the self-graph fixture. This keeps the adapter loader trivially simple and the security surface identical to the already-approved `read_file` command.

**Where it lives:** `{vault_root}/.cerebra/graph.json` — alongside the SQLite vault. The Cerebra CLI writes (or re-writes) this file at the end of every successful ingest run.

### 4.2 Schema: `cerebra/v1`

```json
{
  "schemaVersion": "cerebra/v1",
  "metadata": {
    "schemaVersion": "cerebra/v1",
    "generatedAt": "2026-06-05T12:00:00Z",
    "generator": "cerebra-graph-exporter@v0.1.0",
    "vaultPath": "/home/user/my-vault",
    "cerebraVersion": "0.1.0",
    "stats": {
      "nodeCount": 142,
      "edgeCount": 387,
      "nodesByType": {
        "spine": 8,
        "memory_record": 134
      },
      "edgesByType": {
        "contains": 134,
        "describes": 89,
        "sku-proximity": 120,
        "sku-exact": 44
      },
      "activeSourceCount": 8,
      "activeRecordCount": 134,
      "classifiedRecordCount": 134,
      "unclassifiedRecordCount": 0
    }
  },
  "nodes": [
    {
      "id": "source:src_a3f8b2c1",
      "label": "training-notes.md",
      "fullLabel": "/home/user/my-vault/training-notes.md",
      "type": "spine",
      "cluster": "slate",
      "status": "active",
      "tags": ["source", "markdown"],
      "size": 18,
      "path": "/home/user/my-vault/training-notes.md",
      "lastModified": "2026-06-04T18:30:00Z",
      "raw": {
        "detected_type": "markdown",
        "source_id": "src_a3f8b2c1",
        "record_count": 12,
        "total_tokens": 4800,
        "color": "#6b7280",
        "dimFactor": 1.0,
        "sourceAdapter": "cerebra-vault"
      }
    },
    {
      "id": "record:rec_7d9e2f4a",
      "label": "Ablation Setup",
      "fullLabel": "training-notes.md › Ablation Setup",
      "type": "memory_record",
      "cluster": "gold",
      "status": "active",
      "tags": ["TECHNIQUE", "TEXT", "q1"],
      "size": 7,
      "path": "/home/user/my-vault/training-notes.md",
      "lastModified": "2026-06-04T18:30:00Z",
      "raw": {
        "sku_address": "400000.03.00",
        "d1": 4,
        "d1_category": "TECHNIQUE",
        "d1_confidence": 0.92,
        "d9_modality": "TEXT",
        "d10_provenance": "OBSERVED",
        "quadrant": 1,
        "quadrant_name": "Generative",
        "detected_type": "markdown",
        "token_estimate": 340,
        "chunk_index": 3,
        "heading_path": "Ablation Setup",
        "record_id": "rec_7d9e2f4a",
        "source_id": "src_a3f8b2c1",
        "color": "#e0a84f",
        "dimFactor": 1.0,
        "sourceAdapter": "cerebra-vault"
      }
    }
  ],
  "edges": [
    {
      "id": "edge-src_a3f8b2c1-rec_7d9e2f4a-contains",
      "source": "source:src_a3f8b2c1",
      "target": "record:rec_7d9e2f4a",
      "type": "contains",
      "weight": 0.4,
      "bidirectional": false,
      "provenance": { "source": "cerebra-db", "detail": "source_id FK" },
      "raw": { "label": null, "color": "rgba(107,114,128,0.35)" }
    }
  ]
}
```

### 4.3 Backward compatibility policy

Follows LumaWeave's own convention: breaking field changes bump `schemaVersion`; additive optional fields are backward-compatible without a version bump. The adapter loader checks `schemaVersion === "cerebra/v1"` and rejects anything else with a clear error.

---

## §5 — The adapter registry entry

This is the TypeScript block that would be added to `sourceAdapterRegistry.ts` in LumaWeave:

```typescript
{
  adapterId: "cerebra-vault",
  adapterType: "markdown-vault",   // closest existing type; OR add "cerebra-vault" to SourceAdapterType union
  adapterVersion: "0.1.0",
  inputPattern: {
    type: "path",
    pattern: "**/.cerebra/graph.json",
    examples: [
      "/home/user/my-vault/.cerebra/graph.json",
      "/home/user/projects/knowledge/.cerebra/graph.json",
    ],
  },
  translationSet: {
    nodeMappings: {
      "source":        "spine",
      "memory_record": "memory_record",
    },
    edgeMappings: {
      "contains":      "contains",
      "describes":     "describes",
      "sku-proximity": "tag-overlap",
      "sku-exact":     "explicit-reference",
    },
    defaultConfidence: "observed",
  },
  limits: {
    maxNodes: 2000,
    maxEdges: 10000,
    maxDepth: 2,          // spine → records is exactly depth 2
    maxFileSize: 52428800, // 50MB — a very large vault's graph.json
    timeoutMs: 15000,
  },
  qaReportFormat: {
    requiredFields: ["adapterId", "sourceDescription", "counts", "limits", "safety"],
  },
  status: "candidate",
  contractVersion: "v74a",
  lastUpdated: "2026-06-05T00:00:00Z",
},
```

**Note on `adapterType`:** The `SourceAdapterType` union in `sourceAdapterRegistry.ts` does not currently include `"cerebra-vault"`. Adding it requires a one-line change to that union. The alternative is to reuse `"markdown-vault"` since Cerebra vaults are markdown-based, but that's semantically imprecise. The cleaner choice is to add `"cerebra-vault"` to the union and add a corresponding `adapterType: "cerebra-vault"` value — it's additive and non-breaking.

---

## §6 — The translation set

How Cerebra's native concepts map to LumaWeave's normalized types:

| Cerebra concept | LumaWeave normalized type | Notes |
|---|---|---|
| `source` (spine node) | `spine` | Hub node; represents the file itself |
| `memory_record` | `memory_record` (new) or `doc` (existing) | Leaf knowledge unit |
| `detected_type: markdown` | cluster: `slate` | Source node visual treatment |
| `detected_type: code` | cluster: `gray` | Source node visual treatment |
| D1 quadrant 0 (Empirical) | cluster: `azure` | Record node color |
| D1 quadrant 1 (Generative) | cluster: `gold` | Record node color |
| D1 quadrant 2 (Normative) | cluster: `purple` | Record node color |
| D1 quadrant 3 (Relational) | cluster: `teal` | Record node color |
| `contains` (source→record) | `contains` | Structural, low-weight |
| adjacent chunks in same document | `describes` | Semantic adjacency |
| shared D1 category | `tag-overlap` | Thematic clustering |
| identical sku_address | `explicit-reference` | Exact cognitive co-location |
| `lifecycle_state: active` | `status: "active"` | Pass-through |
| `lifecycle_state: stale` | omit from graph | Stale = superseded, don't visualize |
| `d1_confidence < 0.5` | `raw.dimFactor: 0.7` | Low-confidence records appear dimmed |
| `token_estimate` | `size` (scaled) | Bigger tokens = bigger node |

**Confidence typing** (LumaWeave's `ConfidenceType`):
- `contains` and `describes` edges: `"observed"` — derived directly from FK relationships in the DB
- `sku-proximity` edges: `"inferred"` — inferred from shared classifier output
- `sku-exact` edges: `"observed"` — identical sku_address is a direct DB match

---

## §7 — The update model

### Cerebra side

The graph exporter runs at the end of every successful `cerebra ingest` command. It queries all `active` memory_records with completed sku_assignments, builds the node/edge arrays, and writes `{vault_root}/.cerebra/graph.json`. This is a full rewrite on every ingest — no incremental patching. Ingest runs are already idempotent (unchanged files are skipped), so the graph.json is only rewritten when something actually changed.

The file gets a new `generatedAt` timestamp on every write, which the adapter can use as a change signal.

### LumaWeave side

LumaWeave's current change-detection mechanism is `refreshToken` — an integer in `SourcesSettings` that is incremented to trigger `useGraphSourceSummary` to re-load the source. The `cerebra-vault` adapter would work identically to the self-graph adapter: LumaWeave reads the file when `refreshToken` changes.

**How the user triggers a refresh:** Two options, both consistent with the current app design:

1. **Manual**: User clicks a "Refresh" button in the Graph Sources panel. LumaWeave increments `refreshToken`, re-reads `graph.json`, and re-renders. Simple, requires no file watching.

2. **File-watch (future)**: A Tauri file watcher on `.cerebra/graph.json` increments `refreshToken` automatically when the file's mtime changes. This requires a new Tauri command (a file-system watcher) — out of scope until the basic adapter is shipped and working.

The v1.0 recommendation is manual refresh. It matches the existing UX and avoids new infrastructure.

### Change propagation in detail

```
User runs `cerebra ingest`
  → Cerebra processes changed sources
  → New memory_records created with lifecycle_state='active'
  → Old records for changed sources set to lifecycle_state='stale'
  → Exporter queries all active records + sku_assignments
  → Writes new graph.json (full rewrite, new generatedAt)
  
User clicks Refresh in LumaWeave
  → refreshToken increments
  → useGraphSourceSummary re-fires
  → loadSource("cerebra-vault") reads graph.json
  → adaptCerebraGraphToSigma() maps to LumaWeaveNodeDraft[]
  → buildGraphologyGraph() → Sigma re-renders
```

**What stale records mean visually:** Because stale records are excluded from `graph.json` entirely (not present, not dimmed), a changed source file's old knowledge units simply disappear from the graph on refresh, replaced by the new records. This is clean and correct — the old content is gone; the new content is the truth.

---

## §8 — The adapter lifecycle

### Stage gates

**`candidate`** — entry exists in `sourceAdapterRegistry.ts`, no loader code.  
Gate: TypeScript compiles, `validate-source-adapters.mjs` passes on the entry shape.

**`registered`** — `adaptCerebraGraphToSigma()` loader exists and is wired into `loadSource.ts`.  
Gate: function exists, is dispatched by `adapterId === "cerebra-vault"`, reads `cerebra/v1` schema, emits `LumaWeaveNodeDraft[]`. Typecheck passes. Self-graph E2E still passes (no regression).

**`validated`** — QA report emits, counts match, fixture-based E2E test passes.  
Gate: a fixture `graph.json` (generated from a real or synthetic Cerebra vault) lives in `src/fixtures/`, the adapter processes it, node/edge counts match expected values, no console errors.

**`accepted`** — tested against a live Cerebra vault, graph looks correct, no performance issues within `limits`.  
Gate: developer manually verifies the rendered graph against a real vault. Nodes appear clustered by D1 quadrant, sources appear as hub spines, `sku-exact` edges visibly connect co-located records.

**`active`** — production-ready, shipped.  
Gate: accepted + `docs/LUMAWEAVE_NOW.md` updated to note the adapter as available.

---

## §9 — What needs to be built

### In Cerebra: `cerebra/graph/exporter.py`

The `cerebra/graph/` module already has a stub `__init__.py`. The exporter is a new file there.

**Responsibilities:**
1. Query all `active` sources from the SQLite store
2. For each source, query all `active` memory_records with completed sku_assignments (LEFT JOIN `sku_assignments` on `record_id`, WHERE `lifecycle_state = 'active'`)
3. Build the `cerebra/v1` JSON structure (nodes + edges)
4. Apply caps: max 2000 nodes total (alphabetically by source path, then by chunk_index within source), max 5 sku-proximity edges per record
5. Write to `{vault_root}/.cerebra/graph.json`
6. Return a stats dict for CLI output

**Node building:**
- Source nodes: query `SELECT * FROM sources WHERE lifecycle_state = 'active'`; sum token_estimates per source with a sub-query
- Record nodes: `SELECT mr.*, sa.d1, sa.d1_confidence, sa.d9, sa.d10, sa.sku_address, c.heading_path, c.chunk_index, c.token_estimate FROM memory_records mr JOIN sku_assignments sa ON mr.record_id = sa.record_id JOIN chunks c ON mr.chunk_id = c.chunk_id WHERE mr.lifecycle_state = 'active'`

**Edge building:**
- `contains`: trivially from source_id FK on each record
- `describes`: records from the same document, ordered by chunk_index — link adjacent pairs (chain, not fully connected)
- `sku-proximity`: group records by d1, emit edges within each group (capped at 5 per node, highest-weight first)
- `sku-exact`: group records by full sku_address, emit edges within each group (no cap — exact matches are rare)

**CLI hook:** Add a `--export-graph` flag to `cerebra ingest`, or call `export_graph()` automatically at the end of a successful ingest run. The automatic path is better UX — the graph.json is always fresh after an ingest, no user action needed.

### In LumaWeave: `adaptCerebraGraphToSigma()`

A new adapter function in `src/source-adapter/`, structured identically to `adaptSelfGraphToSigma()` in `self-graph-adapter.ts`. It:

1. Checks `graph.schemaVersion === "cerebra/v1"` and throws a clear error if not
2. Maps each node through cluster → color lookup, type → size lookup
3. Maps each edge through edge-type → color lookup, weight → confidence band
4. Returns `{ nodes: LumaWeaveNodeDraft[], edges: LumaWeaveEdgeDraft[] }`

A new cluster color entry is needed for `purple` (Normative quadrant) — the current `clusterToColor` map in `self-graph-adapter.ts` doesn't include it. Purple = `#a67de8` (already used for `governs` edges, so the color exists in the codebase).

**Registry entry:** Add to `sourceAdapterRegistry.ts` as shown in §5.  
**Dispatch:** Add to `loadSource.ts` alongside the self-graph branch (or after the v109 `registerSourceAdapter()` migration, register the loader in the map).  
**Fixture:** Generate a small synthetic `cerebra-graph.json` to use in E2E tests.

---

## §10 — Design decisions and open questions

### Decided

**Export-file over direct SQLite**: Cerebra writes `cerebra-graph.json`; LumaWeave reads JSON. Follows the self-graph pattern, avoids a SQLite WASM or Rust query dependency in LumaWeave. The file is co-located with the vault so path resolution is trivial.

**Two-tier nodes (spine + record), skip document/chunk**: The hierarchy is real but documents and chunks are pipeline internals. The meaningful visualization is sources (what you wrote) and classified records (what you know).

**Stale records are omitted, not dimmed**: Dimming requires the node to exist; omitting is cleaner and correct. A stale record is superseded knowledge — it shouldn't be in the graph.

**D1 quadrant determines cluster color**: The four quadrants (Empirical/Generative/Normative/Relational) map neatly to four distinct colors from LumaWeave's cluster palette. Within a quadrant, the individual D1 category can be surfaced via tags and the `d1_category` raw field.

**sku-proximity edges capped at 5 per node**: Matches LumaWeave's tag-overlap cap. Without this, a vocabulary-heavy vault (many TECHNIQUE records, for instance) produces a dense edge mess.

**Manual refresh, no file-watching**: Simpler, no new Tauri infrastructure. File-watching is a logical follow-on after the basic adapter is validated.

### Open

**`adapterType` enum**: Add `"cerebra-vault"` to the union, or reuse `"markdown-vault"`? The cleaner answer is to add it — Cerebra is not simply a markdown vault, it's a classified knowledge graph. Requires a one-line change to `SourceAdapterType` in `sourceAdapterRegistry.ts`.

**Records without sku_assignment**: Currently proposed: omit them. Alternative: include them with cluster `gray` and no SKU tags, making them visible as unclassified knowledge. This is a UI decision — omitting keeps the graph clean; including surfaces "I ingested this but haven't classified it yet." Worth revisiting once the exporter exists and we can see what both look like.

**Node label strategy for heading-path-less records**: Records from sources with no heading structure (e.g., a code file that produced one large chunk) have an empty `heading_path`. Current proposal: fall back to document title, then to `record_{id[:8]}`. A better option might be the first 60 characters of the chunk content. Needs experimentation.

**SKU sub-dimensions (D2–D6) in future**: Currently all `0x0` (v1-stub). Once subcategory strategy is filled in, D2/D3 will provide finer-grained clustering within a D1 category. The exporter should include all 10 SKU digits in the raw bag now (they already are, as `sku_address`), so the adapter can be updated to use them without changing the schema.

**Cross-record content references**: When Cerebra eventually detects wikilinks or explicit references within chunk content, those become `explicit-reference` or `wiki-link` edges at weight 1.0 / 0.7 — the same types the self-graph adapter uses for docs. The translation set entry is already declared for `"sku-exact": "explicit-reference"`; a future `"wiki-link": "wiki-link"` entry would slot in without breaking the schema.

---

## Appendix: cluster-to-color reference for the `cerebra-vault` adapter

```typescript
const cerebraClusterToColor: Record<string, string> = {
  // Inherited from self-graph-adapter.ts
  azure:  "#4fa3e0",   // Empirical quadrant records
  gold:   "#e0a84f",   // Generative quadrant records
  teal:   "#4fd9c8",   // Relational quadrant records
  gray:   "#6a7485",   // code sources
  slate:  "#6b7280",   // markdown sources
  // New for cerebra-vault
  purple: "#a67de8",   // Normative quadrant records (already in edge color map)
};
```

```typescript
const cerebraTypeToSize: Record<string, number> = {
  spine:         14,   // source files — medium hubs
  memory_record:  7,   // default; scaled by token_estimate in exporter
};
```

```typescript
const cerebraEdgeTypeToColor: Record<string, string> = {
  "contains":       "rgba(107,114,128,0.35)",
  "describes":      "rgba(79,163,224,0.40)",
  "sku-proximity":  "rgba(100,217,164,0.30)",
  "sku-exact":      "rgba(224,168,79,0.55)",
};
```
