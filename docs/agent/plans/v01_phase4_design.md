# Phase 4 Design — Retrieval Orchestration and ContextPacket

**Status:** Draft v2 — approved; implementation in progress  
**Date:** 2026-06-10  
**Scope:** Design only. No code changes. Locks eight architectural decisions (D1–D8) for the retrieval layer.  
**Demo horizon:** ~one week. Decisions that gold-plate at the cost of demo timing are wrong.

---

## §1. Current State

### What Phase 3 shipped

| Area | Module | State |
|------|--------|-------|
| Migration framework | `cerebra/storage/migrations.py` | Migrations 1–7 applied. Schema v7 on dev vault. WAL journal mode. |
| Vector index | `cerebra/storage/embeddings.py` | mxbai-embed-large-v1, 1024-dim float32. `cosine_search()` returns `list[tuple[str, float]]`. 745 records embedded. |
| Lexical index | `cerebra/storage/lexical.py` | FTS5 virtual table `memory_records_fts`. `search()` returns `list[tuple[str, float]]`. |
| Graph store | `cerebra/storage/graph_store.py` | `upsert_node`, `upsert_edge`, `set_node_lifecycle`, `set_edge_lifecycle`. Polymorphic nodes+edges, RESTRICT FK semantics. |
| Index state | `cerebra/storage/index_state.py` | `is_stale()`, `mark_updated()`, `seed_index_state()`. Tracks lexical/vector/graph freshness. |
| Artifact store | `cerebra/storage/artifact_store.py` | Normalized document artifacts (YAML frontmatter + body). |
| SKU classifier | `cerebra/cognition/sku_classifier.py` | Two-pass classifier. All 745 records have `sku_address` in `sku_assignments`. |
| Score composer | `cerebra/_primitives/score_composer.py` | `compose(components, weights)` → `CompositeScore`. Full component visibility. |
| Inspector events | `cerebra/inspector/` | `make_event()`, `SQLiteEventLog`, `NDJSONEventLog`. Every storage write covered. |

### What Phase 4 builds

A retrieval layer that sits above the indexes and produces inspectable ContextPackets:

```
query text
  → query planner (parse, classify, construct partial SKU)
  → six-step traversal (SKU exact → partial → sibling → vector fallback)
  → salience scorer (weighted multi-component composition)
  → context packet builder (structured output with provenance)
  → retrieval trace writer (full audit trail in substrate)
```

Phase 4 adds no new storage schemas beyond Migration008 (retrieval trace tables). It does not touch ingest, classification, or the graph store's node/edge model.

### Single-commit constraint

Phase 4 is explicitly single-pointer, single-commit SKU. The interpretive lattice (multi-commit per chunk) is a post-v0.1 architectural direction documented in `docs/agent/concepts/interpretive_lattice.md`. Phase 4 must be **designed to be compatible** with eventual multi-commit — the traversal and scoring interfaces should not assume a 1:1 record-to-SKU relationship — but it **implements** only single-pointer retrieval. The specific compatibility constraints are called out in §3 and §4 below.

---

## §2. D1 — Query Interpretation and Planner Architecture

### Decision: heuristic D1 classification + hybrid mode selection

**Rejected alternative:** LLM-based query classification. Adds 300ms–1s latency per query on the demo path. Not worth it at 745 records where vector fallback is always available and fast.

**Rejected alternative:** Embed-the-query-and-use-nearest-neighbor's-D1. Requires a GPU model load (300ms cold start) before deciding which retrieval path to take. Circular — we'd be doing vector work before deciding whether to do vector work.

### Planner architecture

The query planner lives at `cerebra/retrieval/planner.py`. It produces a `QueryPlan` dataclass that drives the traversal.

```python
@dataclass
class QueryPlan:
    raw_query: str
    query_d1: int | None          # inferred D1 hex digit, or None if unclassifiable
    query_d1_d2_d3: str | None    # partial SKU pattern e.g. "0x52" matching D1+D2
    mode: str                     # "hybrid" | "lexical_only" | "vector_only"
    max_candidates: int           # cap passed through to traversal
    staleness_warnings: list[str] # indexes found stale at plan time
```

`query_plan(query: str, db_path: Path) → QueryPlan`

### D1 heuristic classification

The classifier uses a keyword vocabulary matched against the 16 cognitive categories. No LLM call. No embedding.

**Keyword map (initial, tunable):**

| D1 hex | Category | Trigger keywords |
|--------|----------|-----------------|
| 0x0 | OBSERVATION | data, observed, measured, logged, recorded, event, sample |
| 0x1 | PATTERN | pattern, recurrence, trend, regularity, structure across |
| 0x2 | MECHANISM | how it works, causes, process, causal, flow, engine, pipeline |
| 0x3 | PHENOMENON | what is, entity, named, concept, system, thing called |
| 0x4 | TECHNIQUE | how to, method, procedure, approach, strategy, way to |
| 0x5 | DESIGN | architecture, design, structure, plan, spec, decision |
| 0x6 | CREATION | artifact, output, built, produced, created, written |
| 0x7 | TOOL | tool, library, framework, CLI, command, SDK, API |
| 0x8 | PRINCIPLE | should, must, rule, doctrine, principle, policy |
| 0x9 | JUDGMENT | review, evaluate, assess, compare, critique, quality |
| 0xA | GOAL | goal, want, target, objective, aim, intention |
| 0xB | CONSTRAINT | cannot, blocked, limitation, constraint, forbidden, restricted |
| 0xC | EVENT | happened, when, during, session, meeting, incident |
| 0xD | AGENT | who, Ryan, Anthropic, system, agent, team |
| 0xE | CONTEXT | project, scope, environment, setting, context |
| 0xF | RELATION | relationship, between, depends, connects, links |

**Classification rule:** tokenize query, count category hits, select highest-hit category as D1. If no hits, D1 = None (mode falls to hybrid). In case of tie, prefer the category whose keywords appear earlier in the query.

**Keyword vocabulary lives in a config file, not code:** `cerebra/retrieval/d1_keywords.toml`. Calibration will be ongoing as the corpus and query patterns grow; making the vocabulary data rather than code keeps that work cheap (edit TOML, no code review needed). The planner loads this file at startup and caches it. Format: one `[category_hex]` section per D1 value with a `keywords = [...]` list.

This does not need to be perfect. The role of D1 classification is to produce a candidate pre-filter that costs zero LLM tokens. Vector fallback (Step 5) catches whatever SKU traversal misses.

### Mode selection logic

```
query has identifiers/symbols/filenames → "lexical_only"
  (detected: camelCase, snake_case, file extensions, numeric codes, quoted strings)

query is 1-2 words, no keyword hit → "vector_only"
  (too short for reliable keyword matching; go straight to vector)

query >= 3 words with D1 hit → "hybrid"
  (run full six-step traversal; lexical and vector both active)

query >= 3 words, no D1 hit → "hybrid" with D1=None
  (traversal Steps 2-4 produce nothing, falls through to Step 5 naturally)
```

Three modes only — `"hybrid"`, `"lexical_only"`, `"vector_only"`. There is no `"sku_traversal"` mode because the six-step traversal runs for every mode; SKU navigation is part of the traversal structure, not a separate mode. The mode affects which salience components are active (see §4), not whether the traversal runs.

**All modes run the six-step traversal.** The mode affects which signals contribute to salience composition (see §4). The traversal structure is uniform.

### Planner location

```
cerebra/retrieval/planner.py
  - QueryPlan (dataclass)
  - _classify_d1(query: str) -> int | None
  - _detect_mode(query: str, d1: int | None) -> str
  - query_plan(query: str, db_path: Path) -> QueryPlan
```

The planner checks index staleness (§7) as part of `query_plan()` and records any staleness warnings on the returned plan. The retrieval layer propagates these warnings into the ContextPacket's `uncertainties` list.

---

## §3. D2 — Six-Step Traversal

### Decision: all six steps run for every query; empty steps fall through silently

No early exit except Step 2 (explicit early-exit gate below). Every step appends candidates to a running set. By the end of Step 5, the set is scored.

**Multi-commit compatibility note:** The traversal is written against `list[str]` record IDs. It does not assume a 1:1 record-to-SKU relationship. When the interpretive lattice lands in v0.2+, the SKU lookup functions can return multiple record IDs per chunk without changing the traversal interface.

### Step 1 — Query SKU construction

**Input:** `QueryPlan.raw_query`, `QueryPlan.query_d1`  
**Output:** `query_sku_d1: int | None`, `query_sku_pattern: str | None`

Constructs the partial SKU pattern the traversal uses for Steps 2 and 3. For Phase 4, only D1 is reliably inferred (heuristic). D2/D3 are not classified — the heuristic vocabulary doesn't have the subcategory resolution needed, and an LLM call is out of scope.

```
query_sku_pattern = hex(query_d1) if query_d1 else None
```

Phase 5+ will extend this to D2/D3 classification when retrieval planning has more budget.

**Trace annotation:** `"step_1_sku_constructed"` with `query_sku_d1`, `query_sku_pattern`.

### Step 2 — Exact SKU match

**Input:** `query_sku_pattern`  
**Action:** `SELECT record_id FROM sku_assignments WHERE sku_address LIKE 'pattern%' AND lifecycle_state = 'active'`  
**Output:** candidate set

If `query_sku_d1 is None`: Step 2 produces empty set, continue.

**Early exit gate:** If Step 2 returns ≥ 10 candidates with mean salience ≥ 0.60 (evaluated after scoring), the planner may skip Steps 3–4. This is the only explicit early exit. In Phase 4 this gate will rarely trigger — the 745-record corpus is thin per-D1 — but the architecture must support it for when the corpus grows.

**Trace annotation:** `"step_2_exact_sku"` with count.

### Step 3 — Partial SKU match

**Input:** `query_sku_d1` (D1 only; D2/D3 not available in Phase 4)  
**Action:** `SELECT DISTINCT record_id FROM sku_assignments WHERE d1 = ? AND lifecycle_state = 'active'`  
**Output:** candidate set (union with Step 2 results; dedup by record_id)

If Step 2 already returned a large set, Step 3 may return the same records plus some additional ones with different D2/D3. Dedup is by record_id; first-occurrence retrieval_path wins.

**Trace annotation:** `"step_3_partial_sku"` with count.

### Step 4 — Sibling pointer traversal

**Phase 4 implementation: no-op placeholder.**

Multi-pointer fanout (v0.2+) is required for sibling traversal to be meaningful. In v0.1.x, every record has at most one SKU address. Step 4 returns the existing candidate set unchanged and records a trace annotation of `"step_4_sibling_skipped: single-pointer v0.1"`.

The function signature is defined now (`traverse_siblings(candidate_ids, db_path) -> list[str]`) so that the no-op can be replaced in v0.2+ without touching the traversal caller.

### Step 5 — Bounded vector fallback

**Input:** candidate set from Steps 2–4, `QueryPlan.query_text`, `QueryPlan.max_candidates`  
**Algorithm:**

```
1. embed(query) → query_vec   (calls _get_model().encode())
2. IF candidate set is non-empty:
   a. Run cosine_search() over ALL active embeddings (existing behavior)
   b. Merge results with existing candidates by record_id
   c. Candidates already found in Steps 2–4 get their vector score added;
      new candidates from vector-only are added to the set
3. IF candidate set is empty (D1=None, no SKU matches):
   a. Run cosine_search() unrestricted
4. Cap total candidate set at max_candidates (default: 200)
```

**Why unrestricted vector search?** The roadmap specifies "bounded vector fallback on the union of candidates so far." But in Phase 4 with a thin SKU corpus (16 categories, 745 records), Steps 2–4 often return 0–10 records, making "bounded by candidates so far" equivalent to a tiny allowlist. Until the corpus grows to where category-bounded vector search saves meaningful cost (~10k+ records), running unrestricted vector gives better recall with negligible cost penalty (3MB matrix × dot product on CPU < 5ms at 745 records). Record in the trace which mode was used.

**Candidate cap:** 200. The 200 figure comes from `CEREBRA_SKU_ADDRESSING.md §11 Step 5`. At 745 records this cap is never reached; it becomes meaningful around 5k+ records.

**Trace annotation:** `"step_5_vector_fallback"` with query embedded T/F, candidate count before and after.

**Implementation note:** Step 5 splits into 5a (lexical search) and 5b (vector search) as parallel retrieval components. Each emits a separate `TraversalStepCompleted` event with `step_name="lexical_search"` or `step_name="vector_fallback"`. Both are gated by the query mode (lexical_only skips 5b; vector_only skips 5a).

### Step 6 — Trace annotation

**Input:** final candidate set  
**Action:** every candidate in the set gets a `retrieval_path` string assembled from which steps contributed it. Candidate sorting and the 200-cap also happen at this phase, before the list is returned to the caller.

```python
# Examples:
"exact_sku:D1=0x5"
"partial_sku:D1=0x5"
"vector_fallback"
"exact_sku:D1=0x5 + vector_fallback"
```

This is the Cerebra differentiator: retrieval is explainable. Every result knows how it was found.

---

## §4. D3 — Salience Scoring Composition

### Decision: five-component model for Phase 4

**Rejected components (deferred):** `access_frequency` (no access tracking yet), `relationship_centrality` (graph is sparse in Phase 4), `task_relevance` (requires task-type classification of query), `contradiction_penalty` (requires cross-record consistency analysis), `source_authority` (all Phase 4 records are source_chunks with equal authority).

**Phase 4 component set:**

| Component | Source | What it measures | Default weight |
|-----------|--------|------------------|----------------|
| `semantic` | `cosine_search()` score | Vector cosine similarity | 0.40 |
| `lexical` | FTS5 BM25 rank (normalized) | Exact term matching strength | 0.25 |
| `sku_match` | Digit match count / query digits | How closely the SKU address matches | 0.15 |
| `recency` | `record.created_at` | Freshness of the record | 0.10 |
| `lifecycle` | `memory_records.lifecycle_state` | Active vs degraded state | 0.10 |

Weights sum to 1.00.

**Rationale for semantic > lexical (0.40 vs 0.25):** Phase 3 verification showed the vector index produces sensible semantic rankings. The corpus is entirely markdown source chunks — no code symbols, no filenames — so exact term matching is less valuable than semantic understanding. If the corpus evolves to include code, increase lexical weight.

**Rationale for sku_match = 0.15:** SKU classification has noise (two-pass classifier ~80–85% D1 stability on similar content). A modest weight reflects this calibration uncertainty. As corpus grows and calibration audits run, this weight can increase.

### Normalization per component

**semantic** — already in [0, 1] (L2-normalized cosine). No normalization needed.

**lexical** — FTS5 BM25 rank is negative (more negative = better match, e.g., -3.2 beats -0.4). Normalize to [0, 1] within the candidate set using the absolute value directly:
```python
# ranks is list of negative floats from FTS5; more negative = better match
max_abs = max(abs(r) for r in ranks) or 1.0
lexical_score = abs(rank) / max_abs  # 1.0 = best BM25, 0.0 = worst
```
The best match (most negative rank, largest abs) → 1.0. The worst match (least negative, smallest abs) → near 0.0. Records with no lexical match get `lexical = 0.0`.

**sku_match** — count matching non-null query digits:
```python
# query_sku has only d1 in Phase 4
matching = 1 if record_d1 == query_d1 else 0
total_query_digits = 1  # only d1 in Phase 4
sku_match = matching / total_query_digits  # 0.0 or 1.0
```
Records with no SKU (null `sku_address`) get `sku_match = 0.0`.

**recency** — exponential decay with 365-day half-life:
```python
import math
age_days = (now - record.created_at) / 86400
recency = math.exp(-age_days / 365)  # 1.0 today, ~0.37 at one year, ~0.14 at two years
```
This keeps foundational docs (project scope, architecture) from being penalized just for age; the decay is gentle.

**lifecycle** — binary multiplier that the score_composer treats as a weight:
```python
lifecycle = 1.0 if record.lifecycle_state == "active" else 0.0
```
Tombstoned records are excluded before scoring (pre-filter query). Archived/warm records would score 0.0 on lifecycle and sink below the relevance floor (§9). This is the desired behavior for Phase 4.

**Note:** In Phase 4, `lifecycle` is effectively constant at 1.0 for every candidate that reaches the scorer — tombstoned records are removed by the traversal SQL pre-filter, and the dev vault contains no archived or warm records yet. The component slot is reserved for forward compatibility (Phase 5+ will introduce archived record retrieval paths where this weight becomes meaningful). The §9 floor calibration math still holds; the weight simply contributes a fixed 0.10 to every composite score in Phase 4.

### Composition

Use `score_composer.compose()` directly:

```python
from cerebra._primitives.score_composer import compose

score = compose(
    components={
        "semantic": semantic_val,
        "lexical": lexical_val,
        "sku_match": sku_match_val,
        "recency": recency_val,
        "lifecycle": lifecycle_val,
    },
    weights={
        "semantic": 0.40,
        "lexical": 0.25,
        "sku_match": 0.15,
        "recency": 0.10,
        "lifecycle": 0.10,
    },
)
# score.composite — final salience float
# score.components — per-component values
# score.explain() — per-component contribution breakdown
```

### Recording in retrieval trace

Every candidate's `CompositeScore` serializes as:
```json
{
  "composite": 0.73,
  "components": { "semantic": 0.80, "lexical": 0.45, "sku_match": 1.0, "recency": 0.91, "lifecycle": 1.0 },
  "weights": { "semantic": 0.40, "lexical": 0.25, "sku_match": 0.15, "recency": 0.10, "lifecycle": 0.10 },
  "contributions": [ ... ]  // from score.explain()
}
```

Stored in `retrieval_candidates.score_json` (see §5). The `CompositeScore.explain()` method is the "why was this selected" answer for the inspector.

### Multi-commit compatibility note

When lattice multi-commit lands in v0.2+, a chunk may surface via two record IDs (its DESIGN and PRINCIPLE commits). The scorer handles this naturally — each record_id scores independently. Deduplication to avoid showing the same source content twice is a ContextPacket builder responsibility (§4), not a scorer responsibility.

---

## §5. D4 — ContextPacket Structure

### Decision: align CEREBRA_CONTEXT_PACKET_PROTOCOL.md §16 with Phase 3 storage

The protocol doc was written before Phase 3 shipped. The Phase 4 packet uses actual field names from the storage schema.

### JSON schema

```json
{
  "context_packet_id": "ctxpkt_<sha256[:12]>",
  "packet_version": 1,
  "schema_version": 1,
  "created_at": 1720000000,

  "query": "plan the retrieval architecture",
  "mode": "hybrid",

  "is_abstained": false,
  "abstention_rationale": null,

  "retrieval_trace_id": "trace_<sha256[:12]>",
  "origin_event_ids": ["evt_<hex>", "evt_<hex>"],

  "selected_memory": [
    {
      "record_id": "rec_...",
      "source_id": "src_...",
      "chunk_id": "chk_...",
      "content_excerpt": "<first 400 chars of record.content>",
      "source_path": "docs/refined-runtime-model/CEREBRA_RETRIEVAL_ARCHITECTURE.md",
      "sku_address": "0x52.42.04",
      "score": 0.73,
      "score_components": {
        "semantic": 0.80,
        "lexical": 0.45,
        "sku_match": 1.0,
        "recency": 0.91,
        "lifecycle": 1.0
      },
      "retrieval_path": "partial_sku:D1=0x5 + vector_fallback",
      "rank": 1
    }
  ],

  "token_estimate": 4200,
  "selected_count": 5,
  "candidate_count": 47,

  "uncertainties": [],
  "excluded_candidate_count": 42
}
```

### Required vs optional fields

**Required:** `context_packet_id`, `packet_version`, `created_at`, `query`, `mode`, `is_abstained`, `retrieval_trace_id`, `selected_memory`, `token_estimate`, `selected_count`, `candidate_count`

**Optional:** `abstention_rationale` (null when not abstained), `origin_event_ids` (empty list is valid), `uncertainties` (empty list is valid), `excluded_candidate_count`

### Provenance fields

`retrieval_trace_id` links to the `retrieval_traces` table (§6). The 1:1 relationship between a ContextPacket and its trace is invariant — every packet has exactly one trace, every trace produces at most one packet (abstained traces have `context_packet_id = null`).

`origin_event_ids` lists the inspector event IDs emitted during this retrieval: `[QueryReceived.event_id, QueryPlanned.event_id, ContextPacketBuilt.event_id]`. This is the audit chain — a reader can reconstruct the full inspector event sequence from these IDs.

### Abstention form

When the relevance floor is not met (see §9), the packet is:

```json
{
  "context_packet_id": "ctxpkt_...",
  "packet_version": 1,
  "created_at": 1720000000,
  "query": "weather forecast for Beirut",
  "mode": "hybrid",
  "is_abstained": true,
  "abstention_rationale": "No candidates above salience floor 0.35; best score was 0.28",
  "best_score_seen": 0.28,
  "retrieval_trace_id": "trace_...",
  "origin_event_ids": ["evt_...", "evt_...", "evt_..."],
  "selected_memory": [],
  "token_estimate": 0,
  "selected_count": 0,
  "candidate_count": 12,
  "uncertainties": [],
  "excluded_candidate_count": 12
}
```

The `selected_memory` array is always present (empty list, not null) so consumers can iterate without null-checking.

### Versioning

`packet_version` starts at 1. When the schema changes in a future phase, increment this field. Consumers should check `packet_version` before parsing `selected_memory` structure, since that is the most likely field to evolve.

### Token estimation

Simple heuristic: 1 token ≈ 4 characters. `token_estimate = sum(len(item["content_excerpt"]) for item in selected_memory) // 4`. This is a rough budget signal, not a precise count. Phase 5 working memory integration will make this more precise.

---

## §6. D5 — Retrieval Trace Schema

### Decision: three tables in Migration008, same vault database

**Rejected alternative:** separate retrieval.db file. Adds operational complexity. Phase 4's vault is single-file; no reason to split.

### Tables

**`retrieval_traces`** — one row per query attempt

```sql
CREATE TABLE retrieval_traces (
    trace_id          TEXT    PRIMARY KEY,
    query             TEXT    NOT NULL,
    mode              TEXT    NOT NULL,
    query_sku_d1      INTEGER,           -- null if unclassifiable
    query_sku_pattern TEXT,              -- partial SKU pattern used
    plan_json         TEXT    NOT NULL,  -- JSON dump of QueryPlan
    started_at        INTEGER NOT NULL,
    finished_at       INTEGER NOT NULL,
    duration_ms       INTEGER NOT NULL,
    candidate_count   INTEGER NOT NULL,
    selected_count    INTEGER NOT NULL,
    abstained         INTEGER NOT NULL DEFAULT 0,   -- boolean
    context_packet_id TEXT,             -- null on abstention
    schema_version    INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_trace_started ON retrieval_traces(started_at);
CREATE INDEX idx_trace_mode    ON retrieval_traces(mode);
```

**`retrieval_steps`** — one row per traversal step per trace

```sql
CREATE TABLE retrieval_steps (
    step_id          TEXT    PRIMARY KEY,
    trace_id         TEXT    NOT NULL REFERENCES retrieval_traces(trace_id),
    step_number      INTEGER NOT NULL,   -- 1-6
    step_name        TEXT    NOT NULL,   -- "query_sku_construction" | "exact_sku" | "partial_sku" | "sibling_traversal" | "vector_fallback" | "trace_annotation"
    candidate_count  INTEGER NOT NULL,   -- cumulative candidates after this step
    new_candidates   INTEGER NOT NULL,   -- candidates added by this step
    duration_ms      INTEGER NOT NULL,
    skipped          INTEGER NOT NULL DEFAULT 0,
    skip_reason      TEXT,
    schema_version   INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_step_trace ON retrieval_steps(trace_id, step_number);
```

**`retrieval_candidates`** — one row per candidate surfaced

```sql
CREATE TABLE retrieval_candidates (
    candidate_id      TEXT    PRIMARY KEY,
    trace_id          TEXT    NOT NULL REFERENCES retrieval_traces(trace_id),
    record_id         TEXT    NOT NULL,
    step_surfaced     TEXT    NOT NULL,   -- step_name that first produced this record
    retrieval_path    TEXT    NOT NULL,
    salience_score    REAL    NOT NULL,
    score_json        TEXT    NOT NULL,   -- JSON: CompositeScore
    selected          INTEGER NOT NULL DEFAULT 0,   -- boolean
    rank              INTEGER,            -- null if not selected
    exclusion_reason  TEXT,               -- null if selected
    schema_version    INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_cand_trace    ON retrieval_candidates(trace_id, selected);
CREATE INDEX idx_cand_record   ON retrieval_candidates(record_id);
```

### Trace–ContextPacket relationship

1:1. One retrieval → one trace → one packet (or one abstained trace with no packet). A query that returns a cached packet from a prior trace is a separate retrieval with its own trace (no caching in Phase 4; each `cerebra context` call produces a new trace and a new packet).

### Retention semantics

Traces accumulate indefinitely in v0.1.x. No archiving or pruning in Phase 4. At 745 records with expected demo-scale usage (~50 queries), trace storage is negligible. Phase 5/6 should add a `cerebra prune traces --older-than 30d` command when trace volume becomes noticeable.

---

## §7. D6 — Dual Staleness Semantics (Resolution of Q7)

### Background

Q7 (from Phase 3 open questions): `index_state.is_stale(name)` returns True only when `last_updated_at == 0` (never-built check). `lexical.is_lexical_stale()` returns True when `MAX(record.created_at) > index.last_updated_at` (drift detection). These are semantically different, and the retrieval planner needs a unified API.

### Decision: extend `is_stale()` with index-specific drift delegation

**Location:** `cerebra/storage/index_state.py`

Extended signature:
```python
def is_stale(db_path: Path, index_name: str, *, check_drift: bool = True) -> bool
```

Behavior:
1. If `last_updated_at == 0`: return True (never-built, as before)
2. If `check_drift=True` and an index-specific drift detector is registered for `index_name`: delegate to it
3. Otherwise: return False (index exists and no drift detector registered)

**Drift detector registry (Phase 4 scope):**

| Index | Drift detector | Condition |
|-------|---------------|-----------|
| `lexical` | `lexical.is_lexical_stale(db_path)` | `MAX(memory_records.created_at) > index_state.last_updated_at` |
| `vector` | `_vector_has_pending(db_path)` | `pending_embeddings COUNT > 0` |
| `graph` | None (not registered) | Phase 4 does not define graph drift — placeholder |

**When an index is stale at query time:**

Phase 4 does NOT block retrieval on staleness. Blocking would break the demo path when embeddings drift. Instead:
- Add a staleness notice to `QueryPlan.staleness_warnings`
- The ContextPacket builder propagates warnings to `uncertainties` field
- Example uncertainty: `"vector index may be stale: 3 records pending embedding"`
- Emit `StalenessDetected` inspector event (see §11)

**Rationale:** The v0.1.x vault is small enough that a stale vector index (a few pending records) doesn't meaningfully degrade retrieval. Degraded-with-warning is better than blocked for demo timing. Phase 5 can add auto-repair (drain_pending before retrieval) as an optional flag.

### Staleness API surface (implementation contract)

```python
# in index_state.py
def is_stale(db_path: Path, index_name: str, *, check_drift: bool = True) -> bool: ...

# Retrieval planner call pattern:
stale_indexes = [name for name in ("lexical", "vector", "graph") if is_stale(db, name)]
```

---

## §8. D7 — Query Expansion

### Decision: explicit deferral

Phase 4 does not implement query expansion.

**Failing query class documented here (not fixed):**

Phase 3 verification (Q3/Q4) showed colloquial phrasing produces weaker top-1 results than technical phrasing:
- Technical: `"retrieval architecture"` → 0.81 cosine
- Colloquial: `"how does the system find stuff"` → 0.62 cosine

The 0.21 gap is real. However, 0.62 still returns a correct top-1. Expansion would recover 0.05–0.10 of that gap; the implementation cost in Phase 4 (a week of demo time) exceeds that benefit.

**Why not a single synonym-substitution pass?**

Synonym substitution without LLM assistance (wordnet, hard-coded maps) produces expansions that often miss domain-specific vocabulary. `"find stuff"` → `"locate items"` doesn't help Cerebra find `"retrieval architecture"`. LLM-based rephrasing is the right tool, but adds latency and requires a model call on the query path.

**Deferral target:** Phase 6 or Phase 8 (signal pipeline). By Phase 6, Cerebra has LLM integration on the cycle path; the expansion can piggyback on the same model call that evaluates signal quality.

**This deferral is recorded as an explicit design decision, not an oversight.** Future retrieval quality analysis that identifies expansion as the blocking gap should reference this section as the documented context for the deferral.

---

## §9. D8 — Abstention and Relevance Floor

### Decision: composite salience floor at 0.35; abstain rather than return noise

**Relevance floor:** `RELEVANCE_FLOOR = 0.35` (composite salience, post-composition)

This is the minimum score for a candidate to appear in `selected_memory`. Any candidate below this floor is counted in `excluded_candidate_count` but not shown.

**Why 0.35?**

Phase 3 vector verification showed:
- Domain queries: mean top-1 score 0.696 (semantic component alone; composite will differ)
- Adversarial query ("weather forecast"): 0.485 semantic score

With the five-component salience model, pure semantic doesn't directly map to composite. Calibrating: a record with semantic=0.40, lexical=0.0, sku_match=0.0, recency=0.90, lifecycle=1.0 gets composite = 0.40×0.40 + 0.0×0.25 + 0.0×0.15 + 0.90×0.10 + 1.0×0.10 = 0.16 + 0 + 0 + 0.09 + 0.10 = 0.35. This is the designed boundary: a record that looks relevant only by semantic signal, with no lexical or SKU support, barely clears the floor — which is correct behavior. If lexical and SKU match contribute, scores are substantially higher.

**Behavior when no candidates clear the floor:**

1. Return abstained ContextPacket (§5 abstention form)
2. Emit `RetrievalAbstained` inspector event (see §11)
3. `cerebra search` exits with code 1 (no useful results)
4. `cerebra context` exits with code 1

**Why abstain rather than return degraded results?**

The lattice concept doc explicitly notes that silence is load-bearing: "the substrate-level equivalent of the silence operator." A system that returns low-confidence results without flagging them trains the user to expect noise. Abstention with rationale (`"best score was 0.28; floor is 0.35"`) is more honest and more useful for debugging the ingestion and classification pipeline.

**Abstention as training signal:**

`RetrievalAbstained` events are Phase 6+ training material. They identify queries the system cannot currently answer — which is precisely the data needed to drive consolidation, expansion, and future corpus enrichment. The event's `best_score_seen` field lets a future analyst distinguish "corpus gap" (score 0.10) from "floor miscalibration" (score 0.34).

**Per-component floors:** not implemented in Phase 4. A single composite floor is enough for demo-scale operation. Per-component floors (e.g., requiring minimum semantic ≥ 0.20) can be added in Phase 5 when retrieval quality data is available.

---

## §10. Module Structure

```
cerebra/retrieval/
  __init__.py                   # exports: query_plan, run_traversal, score_candidates, build_context_packet
  planner.py                    # QueryPlan, query_plan(), D1 heuristic classifier
  traversal.py                  # run_traversal() → CandidateSet; one function per step
  scorer.py                     # score_candidates(candidates, plan) → list[ScoredCandidate]
  context_packet.py             # ContextPacket (dataclass), build_context_packet(), build_abstained_packet()
  trace.py                      # write_trace(), query_trace(), read_trace(); Migration008 table ops
  abstention.py                 # RELEVANCE_FLOOR constant, should_abstain(), build_abstained_packet()
```

### Key dataclasses

```python
# traversal.py
@dataclass
class RawCandidate:
    record_id: str
    step_surfaced: str
    retrieval_path: str
    semantic_score: float | None
    lexical_score: float | None
    sku_d1_match: bool

# scorer.py
@dataclass
class ScoredCandidate:
    record_id: str
    retrieval_path: str
    score: CompositeScore
    source_path: str
    content_excerpt: str
    sku_address: str | None
    created_at: int
    rank: int | None = None
```

### Guiding principle: each module has one job

`planner.py` does not touch the database (except calling `is_stale()`).  
`traversal.py` reads the database but does not score.  
`scorer.py` computes scores but does not write to the database.  
`trace.py` writes to the database but does not compute scores.  
`context_packet.py` assembles but does not score or write.  

This separation makes each module independently testable without mocking the full pipeline.

---

## §11. Inspector Events

New retrieval-layer events. All follow the standard envelope from `cerebra/inspector/event.py`.

### QueryReceived

```python
{
  "event_type": "QueryReceived",
  "actor": "retrieval",
  "summary": "Query received: '<first 60 chars>'",
  "data": {
    "query": "<full query text>",
    "mode_hint": "hybrid",  # before planning; may change after plan
    "vault_path": "<str>"
  },
  "subject_id": "<trace_id>"
}
```

### QueryPlanned

```python
{
  "event_type": "QueryPlanned",
  "actor": "retrieval.planner",
  "summary": "Query planned: mode=hybrid, D1=0x5",
  "data": {
    "trace_id": "<str>",
    "query_sku_d1": 5,          # or null
    "query_sku_pattern": "0x5", # or null
    "mode": "hybrid",
    "staleness_warnings": []    # list of stale index names
  },
  "subject_id": "<trace_id>"
}
```

### TraversalStepCompleted

```python
{
  "event_type": "TraversalStepCompleted",
  "actor": "retrieval.traversal",
  "summary": "Step 3 partial_sku: 12 candidates",
  "data": {
    "trace_id": "<str>",
    "step_number": 3,
    "step_name": "partial_sku",
    "candidate_count": 12,
    "new_candidates": 7,
    "duration_ms": 4,
    "skipped": False,
    "skip_reason": null
  },
  "subject_id": "<trace_id>"
}
```

One event per step (6 total per retrieval). Step 4 fires with `skipped=True, skip_reason="single-pointer v0.1"`.

### SalienceScored

```python
{
  "event_type": "SalienceScored",
  "actor": "retrieval.scorer",
  "summary": "Scored 47 candidates; top=0.83, mean=0.54, floor=0.35",
  "data": {
    "trace_id": "<str>",
    "candidate_count": 47,
    "above_floor": 23,
    "top_score": 0.83,
    "mean_score": 0.54,
    "floor_used": 0.35,
    "weights": { "semantic": 0.40, "lexical": 0.25, "sku_match": 0.15, "recency": 0.10, "lifecycle": 0.10 }
  },
  "subject_id": "<trace_id>"
}
```

### ContextPacketBuilt

```python
{
  "event_type": "ContextPacketBuilt",
  "actor": "retrieval.context_packet",
  "summary": "ContextPacket built: 5 records selected, ~4200 tokens",
  "data": {
    "context_packet_id": "<str>",
    "trace_id": "<str>",
    "query": "<str>",
    "selected_count": 5,
    "candidate_count": 47,
    "token_estimate": 4200,
    "is_abstained": False
  },
  "subject_id": "<context_packet_id>"
}
```

### RetrievalAbstained

```python
{
  "event_type": "RetrievalAbstained",
  "actor": "retrieval",
  "summary": "Abstained: best score 0.28 < floor 0.35",
  "data": {
    "trace_id": "<str>",
    "query": "<str>",
    "mode": "hybrid",
    "query_sku_d1": null,
    "candidate_count": 12,
    "best_score_seen": 0.28,
    "floor": 0.35
  },
  "subject_id": "<trace_id>"
}
```

### StalenessDetected

```python
{
  "event_type": "StalenessDetected",
  "actor": "retrieval.planner",
  "summary": "Index 'vector' is stale: 3 records pending embedding",
  "data": {
    "index_name": "vector",      # "lexical" | "vector" | "graph"
    "last_updated_at": 1719990000,
    "never_built": False,
    "drift_detected": True,
    "drift_detail": "3 records in pending_embeddings"
  },
  "subject_id": "<index_name>"
}
```

---

## §12. CLI Surface

### `cerebra search "<query>"`

Returns ranked records with scores, source paths, and excerpts. Intended as the quick-lookup surface.

**Default output (plain text):**

```
$ cerebra search "retrieval architecture"

Query: "retrieval architecture"  Mode: hybrid  D1: DESIGN (0x5)
Candidates: 47  Above floor: 12  Duration: 43ms

Rank  Score   Source                                           Excerpt
----  ------  -----------------------------------------------  -------
   1  0.83    docs/refined-runtime-model/CEREBRA_RETRIEVAL_A…  Cerebra should not rely on a single…
   2  0.71    docs/agent/plans/v01_phase3_design.md            Phase 3 roadmap tasks (from CEREBRA…
   3  0.68    docs/refined-runtime-model/CEREBRA_DEV_ROADMAP  Tasks: 1. Query planner (cerebra/re…
   4  0.61    docs/refined-runtime-model/CEREBRA_SKU_ADDRESSI  SKU retrieval is attention-budgeted…
   5  0.57    docs/refined-runtime-model/CEREBRA_SALIENCE_SCO  Retrieval should be: hybrid layered…

Retrieval paths:
  #1: partial_sku:D1=0x5 + vector_fallback
  #2: partial_sku:D1=0x5 + vector_fallback
  #3: vector_fallback
  #4: partial_sku:D1=0x5
  #5: vector_fallback
```

**`--format json` output:** full `ScoredCandidate` list as JSON array, one object per line.

**`--limit N`:** default 10. Max 200 (the traversal cap).

**`--explain`:** add full score breakdown per result (calls `score.explain()`).

**`--floor FLOAT`:** override the default relevance floor for this query.

**Exit codes:**
- `0` — results returned
- `1` — abstained (no candidates above floor); prints abstention rationale to stderr
- `2` — error (vault not found, migration not run, etc.)

### `cerebra context "<task>"`

Produces a ContextPacket for downstream consumption. Intended for agent integration.

**Default output (plain text):**

```
$ cerebra context "plan the Phase 4 retrieval implementation"

ContextPacket  ID: ctxpkt_a3f8b2c1d4e5
Query:  plan the Phase 4 retrieval implementation
Mode:   hybrid  |  Trace: trace_7b9d3e...  |  Duration: 51ms

Selected memory (5 records, ~4200 tokens):

[1] CEREBRA_RETRIEVAL_ARCHITECTURE.md  |  Score: 0.83  |  partial_sku:D1=0x5
    Cerebra should not rely on a single retrieval method. A strong memory runtime needs
    layered retrieval because different questions require different access paths...

[2] v01_phase3_design.md  |  Score: 0.71  |  partial_sku:D1=0x5 + vector_fallback
    Phase 3 roadmap tasks (from CEREBRA_DEV_ROADMAP_v8.1.md §Phase 3)...

...

Uncertainties: none
```

**`--format json`:** emits the full ContextPacket JSON schema (§5).

**`--limit N`:** maximum records in `selected_memory`. Default: 10.

**`--out FILE`:** write JSON packet to FILE instead of stdout.

**Exit codes:** same as `cerebra search`.

### No `--vault` flag in Phase 4

The CLI reads vault path from config (same pattern as existing commands). Explicit `--vault` can be added in Phase 5 or 6 when multi-vault operations are relevant.

---

## §13. Open Questions and Risks

**Q1 — D1 keyword classifier calibration.** The keyword vocabulary in §2 is a first draft. It will misclassify queries that use unusual phrasing. The risk is low for Phase 4 (misclassification falls through to vector fallback) but should be empirically validated against the demo query set before declaring Phase 4 complete. Calibration is cheap: run 10 representative queries, check that D1 classification is plausible, adjust keywords as needed.

**Q2 — Migration008 scope.** The three retrieval trace tables (`retrieval_traces`, `retrieval_steps`, `retrieval_candidates`) should land in a single Migration008. No other schema changes are expected. If the ContextPacket design (§5) evolves during implementation, a Migration009 for any additional columns is preferred over editing Migration008 (forward-only invariant).

**Q3 — `cerebra search` vs six-step traversal.** The CLI command `cerebra search` is scoped to "quick lookup." An open question is whether it should run the full six-step traversal or a shorter path (Steps 2, 3, 5 only, skipping step 4 explicitly rather than via no-op). Decision for implementation: run full traversal in both commands. The extra 2ms for the step-4 no-op is negligible. One traversal codepath is simpler to test and maintain.

**Q4 — Token budget for `cerebra context`.** The CLI doesn't know the downstream consumer's context window. Default: include up to 10 records (configurable via `--limit`). The `token_estimate` field in the packet lets callers make their own budget decisions. Actual budget-aware pruning (filling to a target token count) is Phase 5 working memory territory.

**Q5 — Graph staleness.** The `graph` index has no drift detector registered in Phase 4. `is_stale("graph")` returns True only if never-built (last_updated_at == 0). The graph store is already seeded post-Phase 3 with whatever was added by the ingest pipeline. A meaningful drift detector for graph would track "records without corresponding graph nodes" — this requires a join and is Phase 5 scope. For Phase 4: no graph staleness warning.

**Q6 — Sorting tie-breaking.** When two candidates have equal composite scores (e.g., both 0.73), the final rank ordering is deterministic but arbitrary (Python sort stability). In Phase 4 this is fine — ties are rare with floating-point scores. If ties become frequent (e.g., all records with exact SKU match score identically on non-semantic components), add `created_at DESC` as a secondary sort key.

**Q7 — Excerpt length.** The `content_excerpt` field in `selected_memory` is spec'd at 400 chars (see §5). This may be too short for some chunks. Implementation should make excerpt length configurable via a constant (`EXCERPT_MAX_CHARS = 400`) that can be changed without interface breakage.

**~~Q8~~** *(resolved in v2)* Lexical normalization formula was inverted in draft v1. Corrected in §4: `lexical_score = abs(rank) / max_abs`. Unit test in `tests/unit/test_scorer.py::test_lexical_normalization_direction` pins best-BM25→1.0 / worst-BM25→0.0. No open question remains here.

---

## §14. Phase 4 Task Ordering

**Principle:** demo-critical items first; gold-plating deferred or cut.

The demo-critical path is: `cerebra search` returning ranked results with scores and source paths. `cerebra context` producing a ContextPacket. Everything else is built in service of those two commands.

### Task sequence

**Step 1 — Migration008 (retrieval trace tables)**  
Creates `retrieval_traces`, `retrieval_steps`, `retrieval_candidates`. Comes first so every subsequent step can write traces from day one. No code changes to existing modules. Tests: migration idempotency, table creation, FK constraints.

**Step 2 — Module scaffold**  
Create `cerebra/retrieval/__init__.py` and stubs for `planner.py`, `traversal.py`, `scorer.py`, `context_packet.py`, `trace.py`, `abstention.py`. All stubs raise `NotImplementedError`. Verifies import paths before any logic lands.

**Step 3 — Planner (`planner.py`)**  
Implement `_classify_d1()`, `_detect_mode()`, `query_plan()`. No DB calls except `is_stale()` (extend `index_state.is_stale()` here with drift delegation). Tests: D1 classification for all 16 categories, mode selection logic, staleness warnings propagated.

**Step 4 — Traversal steps 2, 3, 5 (`traversal.py`)**  
Steps 2 (exact SKU), 3 (partial SKU), and 5 (bounded vector fallback) are the only steps that produce candidates. Implement these first. Step 4 (sibling, no-op) and step 1/6 (construct/annotate) are trivial wrappers — implement them once steps 2, 3, 5 work. Tests: step 2 returns exact SKU matches, step 3 expands correctly, step 5 calls `cosine_search()`, full traversal produces a non-empty candidate set on the dev vault.

**Step 5 — Scorer (`scorer.py`)**  
Implement `score_candidates()`. Uses `score_composer.compose()`. Tests: each component computes correctly, weights sum to 1.0, tombstoned records not present (pre-filter happens in traversal SQL), lexical normalization boundary case (Q8 above), recency decay.

**Step 6 — `cerebra search` CLI command**  
Wire planner → traversal → scorer → tabular output. At this point the demo "cerebra search works" milestone is met. Tests: smoke test on dev vault, `--format json` produces parseable output, `--limit` respected.

**Step 7 — Trace writer (`trace.py`)**  
Implement `write_trace()`. Insert `retrieval_traces`, `retrieval_steps`, `retrieval_candidates` rows after each retrieval. Add `emit_retrieval_events()` for the inspector event chain (§11). Tests: trace row exists after search, candidate count matches, step rows present.

**Step 8 — ContextPacket builder (`context_packet.py`)**  
Implement `build_context_packet()` and `build_abstained_packet()`. Token estimate, provenance linking, plain-text renderer. Tests: packet schema validates, abstained form has empty `selected_memory`, `origin_event_ids` populated.

**Step 9 — `cerebra context` CLI command**  
Wire planner → traversal → scorer → context packet → output. Demo milestone: `cerebra context "task"` produces structured output. Tests: JSON output matches schema, plain text renderer produces readable output.

**Step 10 — Abstention (`abstention.py`)**  
Implement floor check and abstained packet path. Tests: query that matches nothing returns exit code 1 and abstained packet, `RetrievalAbstained` event emitted.

**Step 11 — Integration tests**  
End-to-end: ingest a doc → classify it → `cerebra search` for it → `cerebra context` with it → inspect the trace. This is the "Cerebra works" demo test. Must pass before Phase 4 is declared complete.

### Deferred within Phase 4

These are in-scope per the roadmap but can land after the demo if time is tight:

- `--explain` flag on `cerebra search` (pretty-prints `score.explain()`)
- Trace pruning command (`cerebra prune traces`)
- Lexical staleness warning in the ContextPacket uncertainties field (the staleness check happens; the warning propagation to the packet is a UI concern)
- Graph neighborhood in ContextPacket (the `graph_context` field from the protocol doc — Phase 5 territory)

### Explicitly out of scope for Phase 4

- Query expansion (§8 — deferred to Phase 6+)
- Sibling pointer traversal (§3 Step 4 — no-op, v0.2 territory)
- Budget-aware context pruning (Phase 5 working memory)
- `--vault` flag on CLI (Phase 5 multi-vault)
- ContextPacket caching (Phase 5+)
- Self-improving retrieval via bandit (§12 of SKU doc — Phase 8+)

---

*Design approved 2026-06-10. Weights (0.40/0.25/0.15/0.10/0.10), floor (0.35), all-six-steps, and abstention semantics confirmed. Implementation underway per §14 task ordering.*
