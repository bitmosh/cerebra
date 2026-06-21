# Cerebra — SKU Addressing System & Retrieval Layer

---

## 1. SKU Address Format (`cerebra/cognition/sku.py`)

The SKU (Stock-Keeping Unit) address is a 12-character string with two dots that encodes the cognitive position of a memory record.

```
D1D2D3D4D5D6.D7D8.D9D10
│             │     │
│             │     └─ Tag byte: D9 (modality) + D10 (provenance)
│             └─ Entry byte: D7D8 (0x00–0xFF, up to 256 entries per location)
└─ Location: 6 hex nibbles (D1=category, D2-D6=subcategory stubs)
```

**Examples:**
- `"040000.01.00"` = D1=TECHNIQUE(0x4), D2-D6 stubs, entry=0x01, TEXT+OBSERVED
- `"8c0000.00.10"` = D1=PRINCIPLE(0x8), JUDGMENT sub-area (0xC?), entry=0x00, CODE+OBSERVED

**Phase 2 stubs:** D2=D3=D4=D5=D6=0x0 for all records. Subcategory expansion is future work.

### SKUAddress dataclass

```python
@dataclass(frozen=True)
class SKUAddress:
    d1: int          # 0x0–0xF (D1Category value)
    d2: int = 0      # stub
    d3: int = 0      # stub
    d4: int = 0      # stub
    d5: int = 0      # stub
    d6: int = 0      # stub
    d7: int          # entry high nibble
    d8: int          # entry low nibble
    d9: int          # D9Modality value
    d10: int         # D10Provenance value
    
    def to_hex_string(self) -> str
    
    @classmethod
    def from_hex_string(cls, s: str) -> "SKUAddress"
```

### SKUAssignment dataclass

```python
@dataclass
class SKUAssignment:
    assignment_id: str                  # uuid
    record_id: str
    sku_address: str                    # hex string
    d1_category: str                    # D1Category name
    classifier_version: str
    prompt_version: str
    subcategory_strategy_version: str
    confidence: float
    raw_scores_json: str | None         # full quadrant+category score JSON
    assigned_at: int
    
    def as_dict(self) -> dict           # for DB insert
```

---

## 2. D1 Category System (`cerebra/cognition/sku_categories.py`)

### D1Category enum (16 values)

```python
class D1Category(IntEnum):
    # Quadrant I — Empirical (0x0–0x3): facts, data, mechanisms
    OBSERVATION  = 0x0   # raw data, measurements, recorded events
    PATTERN      = 0x1   # regularities, correlations, trends
    MECHANISM    = 0x2   # causal processes, how things work
    PHENOMENON   = 0x3   # observable occurrences, discoveries

    # Quadrant II — Generative (0x4–0x7): techniques, designs, creations
    TECHNIQUE    = 0x4   # methods, procedures, algorithms
    DESIGN       = 0x5   # architectures, plans, blueprints
    CREATION     = 0x6   # artifacts, products, implementations
    TOOL         = 0x7   # instruments, frameworks, software

    # Quadrant III — Normative (0x8–0xB): principles, judgments, goals
    PRINCIPLE    = 0x8   # rules, laws, axioms, norms
    JUDGMENT     = 0x9   # evaluations, critiques, assessments
    GOAL         = 0xA   # objectives, intentions, desired states
    CONSTRAINT   = 0xB   # limits, restrictions, requirements

    # Quadrant IV — Relational (0xC–0xF): events, agents, contexts
    EVENT        = 0xC   # occurrences, milestones, incidents
    AGENT        = 0xD   # people, systems, entities that act
    CONTEXT      = 0xE   # settings, environments, situations
    RELATION     = 0xF   # connections, dependencies, associations
```

Quadrant extraction: `quadrant = (d1_value >> 2) & 0x3`
- 0 = Empirical, 1 = Generative, 2 = Normative, 3 = Relational

`CATEGORY_DESCRIPTIONS: dict[D1Category, str]` maps each value to a one-line description used verbatim in classification prompts.

---

## 3. D9 Modality & D10 Provenance (`cerebra/cognition/sku.py`)

### D9Modality

```python
class D9Modality(IntEnum):
    TEXT         = 0x0
    CODE         = 0x1
    GRAPH        = 0x2
    CONVERSATION = 0x3
    OBSERVATION  = 0x4
    DECISION     = 0x5
    SYNTHESIS    = 0x6
    UNKNOWN      = 0x7
```

For ingested records: `d9_from_detected_type(detected_type) → D9Modality` (heuristic, no LLM).
- `.md`, `.txt` → TEXT
- `.py`, `.ts`, `.rs`, etc. → CODE
- default → TEXT

### D10Provenance

```python
class D10Provenance(IntEnum):
    OBSERVED     = 0x0   # ingested from external source (default for ingest)
    CONSOLIDATED = 0x1   # merged/consolidated from multiple records
    SYNTHESIZED  = 0x2   # LLM-generated synthesis
    USER_PIN     = 0x3   # manually added by user
    EXTERNAL     = 0x4   # from external system (not directly ingested)
    SYSTEM       = 0x5   # system-generated (e.g. governance defaults)
    UNKNOWN      = 0x6
```

D10 is always `OBSERVED (0x0)` for records ingested via `cerebra ingest`. Cycle episodes get `SYNTHESIZED (0x2)`.

---

## 4. SKU Classifier (`cerebra/cognition/sku_classifier.py`)

### Version constants

```python
CLASSIFIER_VERSION           = "1.0.0"
PROMPT_VERSION               = "2.0.0"
SUBCATEGORY_STRATEGY_VERSION = "v1-stub"
HIGH_CONF_THRESHOLD          = 0.5
D1_ANCHOR_THRESHOLD          = 0.4
```

### Two-pass classification

**Pass 1 — classify_quadrant(content):**
- Prompt: asks LLM to score content against 4 quadrant descriptions
- Response: JSON `{scores: {Empirical: F, Generative: F, Normative: F, Relational: F}, primary: "...", reasoning: "..."}`
- Primary quadrant = highest score; confidence = primary_score
- Retried once on parse failure

**Pass 2 — classify_within_quadrant(content, quadrant):**
- Prompt: asks LLM to score content against the 4 categories in the winning quadrant
- Response: JSON `{scores: {CATEGORY_A: F, ...}, primary: "...", confidence: F, reasoning: "..."}`
- D1 answer = primary category in winning quadrant
- Retried once on parse failure

Response parsing in `_parse_classification_response()` handles three formats:
1. Canonical nested JSON (expected)
2. Flat JSON (LLM sometimes flattens)
3. Malformed — regex fallback to extract numeric scores

### `classify_record(record_id, content, detected_type) → SKUAssignment | None`

- Idempotency: skips if existing assignment has matching `classifier_version + prompt_version`
- On reclassification: deletes old `sku_assignments` row, re-inserts
- On success: calls `store.insert_sku_assignment()` + `store.update_record_sku()`
- Emits: `SKUAssigned` (new) or `SKUReclassified` (update)
- If `confidence < HIGH_CONF_THRESHOLD (0.5)`: also emits `ClassificationLowConfidence`
- On unrecoverable error: emits `ClassificationFailed`, returns None

### `classify_record_lattice(record_id, content, detected_type, threshold=None) → list[str]`

Runs the same two-pass classification, then passes all category scores to `evaluate_lattice()`.

If `LatticeDecision.should_multi_commit` (≥2 categories ≥ threshold):
- Builds sibling records in `memory_records` for each secondary category
- Sibling `record_id = "rec_" + sha256(f"{primary_record_id}:{category}")[:12]` (deterministic)
- Siblings share the same chunk_id/document_id/source_id as the primary
- Sets `is_lattice_member=True`, `lattice_lineage_id`, `lattice_confidence` on all involved records
- Emits ONE `LatticeCommit` event per chunk (not per sibling) to avoid over-emission
- Returns `[primary_record_id, sibling1_record_id, ...]` (primary always first)

### BackfillReport

```python
@dataclass
class BackfillReport:
    records_found: int
    classified: int
    skipped: int          # already classified with matching version
    failed: int           # ClassificationFailed events
    low_confidence: int   # ClassificationLowConfidence events
    elapsed_ms: int
```

---

## 5. Lattice Evaluation (`cerebra/cognition/lattice.py`)

```python
LATTICE_COMMIT_THRESHOLD = 0.65
```

### LatticeDecision

```python
@dataclass
class LatticeDecision:
    all_scores: dict[str, float]        # category name → score (all 16)
    candidates: list[str]               # categories ≥ threshold
    primary: str                        # highest score category
    should_multi_commit: bool           # True if ≥ 2 candidates

def evaluate_lattice(
    scores: dict[str, float],
    threshold: float | None = None,     # default: LATTICE_COMMIT_THRESHOLD
) -> LatticeDecision
```

`should_multi_commit` is True when `len(candidates) >= 2` (at least two categories scored ≥ threshold). This drives sibling record creation.

### Helpers

```python
def new_lineage_id() -> str                              # "lat_" + uuid[:12]
def build_sibling_record_id(primary_id, category) -> str # deterministic sha256
```

Sibling IDs are deterministic so re-running classification produces the same IDs (idempotent).

---

## 6. Retrieval Planner (`cerebra/retrieval/planner.py`)

### QueryPlan

```python
@dataclass
class QueryPlan:
    trace_id: str           # "trace_" + uuid[:12]
    query: str
    mode: str               # "lexical" | "vector" | "hybrid"
    max_candidates: int     # cap passed to traversal
    d1_hint: str | None     # detected D1 category for SKU traversal
    created_at: int
```

### Mode detection rules

Mode is auto-detected from query characteristics:

| Condition | Mode |
|---|---|
| Query contains code identifiers (`_IDENTIFIER_RE` matches) | `lexical_only` |
| Query length ≤ 2 words AND no D1 keyword hit | `vector_only` |
| Default (all other cases) | `hybrid` |

`_IDENTIFIER_RE` matches: `snake_case_words`, `camelCaseWords`, `.file.extensions`, `"quoted strings"`, `` `backtick wrapped` ``, `ALL_CAPS_CONSTANTS`.

D1 keyword detection uses `d1_keywords.toml` — a TOML file with hex keys (e.g., `"0x5"` for DESIGN) mapping to keyword vocabulary lists. A D1 match sets `d1_hint` in the QueryPlan.

### `RetrievalPlanner.plan(query) → QueryPlan`

1. Detect mode
2. Assign trace_id
3. Emit `QueryReceived` inspector event
4. Emit `QueryPlanned` inspector event (includes mode + d1_hint)
5. Return QueryPlan

---

## 7. Retrieval Traversal (`cerebra/retrieval/traversal.py`)

```python
def traverse(
    db_path: Path,
    plan: QueryPlan,
    event_log: SQLiteEventLog | None = None,
) -> list[CandidateRecord]
```

Six steps execute sequentially. Empty results from a step fall through silently (no abort). Each step annotates candidates with which step found them (for `retrieval_path` field).

### Step 1: `exact_sku`

SQL: `WHERE sku_address = plan.d1_hint` (exact SKU address match, if `d1_hint` set).

Emits `TraversalStepCompleted` with `step_name="exact_sku"`, `candidate_count=N`.

### Step 2: `partial_sku`

SQL: `WHERE sku_address LIKE 'd1_prefix%'` — D1 prefix match (first hex nibble matches `d1_hint`).

Only runs if `d1_hint` is set and `exact_sku` returned < `plan.max_candidates`.

### Step 3: `sibling_traversal`

v0.1 stub — returns input candidates unchanged (no-op). Reserved for future lattice sibling expansion.

### Step 4: `lexical_search`

Calls `lexical.search(db_path, plan.query, limit=plan.max_candidates)`.

Only runs if `plan.mode` is `lexical_only` or `hybrid`.

Returns `[(record_id, rank)]` where rank is negative (FTS5 convention).

### Step 5: `vector_fallback`

Calls `embeddings.cosine_search(db_path, plan.query, limit=plan.max_candidates)`.

Only runs if `plan.mode` is `vector_only` or `hybrid`.

### Step 6: `trace_annotation`

Not a search step — annotates each accumulated candidate with its `retrieval_path` (which steps surfaced it) and deduplicates by record_id (keeping best score seen across steps).

Final sort: `semantic_score DESC`, then `abs(lexical_score) DESC` (tiebreak). Cap at `plan.max_candidates`.

---

## 8. Composite Scorer (`cerebra/retrieval/scorer.py`)

### Salience formula

```
composite = (semantic   × 0.40)
          + (lexical    × 0.25)
          + (sku_match  × 0.15)
          + (recency    × 0.10)
          + (lifecycle  × 0.10)
```

### Component derivations

**Semantic score:** raw cosine similarity from `embeddings.cosine_search()` (already 0–1).

**Lexical score:** FTS5 rank negated and normalized. FTS5 returns negative ranks; the negation gives a positive "goodness" score. Normalized to [0, 1] across the candidate set.

**SKU match score:**
- `1.0` — sku_address matches `plan.d1_hint` exactly
- `0.5` — sku_address D1 nibble matches `plan.d1_hint` D1 nibble (partial)
- `0.0` — no match or no d1_hint

**Recency score:** `math.exp(-age_days / 365)` — exponential decay. A record created today scores 1.0; a 1-year-old record scores ~0.37.

**Lifecycle score:** Always `1.0` in Phase 4. Tombstoned records are pre-filtered before scoring, so lifecycle scoring isn't needed in practice. Reserved for future partial-lifecycle scoring.

### ScoredCandidate

```python
@dataclass
class ScoredCandidate:
    record_id: str
    semantic_score: float
    lexical_score: float
    sku_match_score: float
    recency_score: float
    lifecycle_score: float
    composite_score: float
    content_excerpt: str        # first 300 chars
    retrieval_path: str         # "exact_sku+lexical" etc.
    exclusion_reason: str | None  # set by dedup_siblings or floor filter
    # lattice fields (set by dedup_siblings):
    lattice_sibling_count: int | None
    lattice_winner_record_id: str | None
    lattice_routing_basis: str | None

def explain(self) -> list[dict]:
    # Returns: [{component, value, weight, contribution}, ...]
```

---

## 9. Lattice Deduplication (`cerebra/retrieval/lattice_dedup.py`)

When multiple records share the same `lattice_lineage_id` (siblings), at most one reaches the context packet. Dedup runs after scoring, before floor filtering.

### `dedup_siblings(scored, query_d1, db_path, trace_id, event_log=None) → list[ScoredCandidate]`

Groups candidates by `lattice_lineage_id`. For each group, selects one winner via D2 routing:

**D2 routing rules (applied in priority order):**

1. `sku_match` — exactly one sibling's sku_address D1 matches `query_d1` → that sibling wins
2. `sku_match_multi` — multiple siblings' D1 matches `query_d1` → highest composite wins (tiebreak: earliest `created_at`)
3. `composite_score` — no D1 match → highest composite wins (tiebreak: earliest `created_at`)

Losers receive `exclusion_reason = "lattice_sibling"`.

All group members (winner + losers) receive:
- `lattice_sibling_count` — total group size
- `lattice_winner_record_id` — record_id of the winner
- `lattice_routing_basis` — which rule applied (`"sku_match"`, `"sku_match_multi"`, or `"composite_score"`)

Emits `LatticeSiblingResolved` inspector event per group.

### `dedup_memory_items(items, db_path) → list[MemoryItem]`

Used by `TruthTower.promote_to_t1()` for dedup before tower insertion. No DB updates, no events (pure in-memory filter).

---

## 10. ContextPacket (`cerebra/retrieval/context_packet.py`)

### MemoryItem

```python
@dataclass
class MemoryItem:
    record_id: str
    source_id: str
    chunk_id: str
    content_excerpt: str    # max 400 chars (truncated from content)
    source_path: str        # vault-relative path
    sku_address: str | None
    score: float            # composite score
    score_components: dict[str, float]  # {"semantic": F, "lexical": F, ...}
    retrieval_path: str     # which traversal steps surfaced this
    rank: int               # 1-indexed position in selected_memory
```

### ContextPacket

```python
@dataclass
class ContextPacket:
    context_packet_id: str          # "ctxpkt_" + uuid[:12]
    packet_version: int
    schema_version: int
    created_at: int
    query: str
    mode: str
    is_abstained: bool              # True if floor not met by any candidate
    abstention_rationale: str | None
    retrieval_trace_id: str
    origin_event_ids: list[str]     # event IDs of upstream events
    selected_memory: list[MemoryItem]   # top N after floor filter
    token_estimate: int
    selected_count: int
    candidate_count: int            # total before floor filter
    uncertainties: list[str]
    excluded_candidate_count: int
    best_score_seen: float | None   # populated on abstained packets only
    truth_tower: dict | None        # set by to_tower_field() if called
```

### `build_context_packet(trace_data, scored_candidates, db_path, *, limit=10, event_log=None) → ContextPacket`

Called when at least one candidate clears the floor (`_RETRIEVAL_FLOOR = 0.35`). Selects top `limit` candidates, truncates content to 400 chars per item, sets `truth_tower` field if `TruthTower.to_tower_field()` returns data.

Side effects:
- `UPDATE retrieval_traces SET context_packet_id = ...`
- Emit `ContextPacketBuilt` inspector event

### `build_abstained_packet(trace_data, best_score_seen, *, event_log=None) → ContextPacket`

Called when no candidates clear the floor. Returns packet with `is_abstained=True`, `selected_memory=[]`. Does NOT update `retrieval_traces.context_packet_id`.

### `render_text(packet, limit=10) → str`

Renders packet as structured text for injection into LLM prompt. §12 format (numbered sections with source attribution).

---

## 11. Retrieval Data Flow

```
query (str)
  └─ RetrievalPlanner.plan(query)
       → QueryPlan (mode, trace_id, d1_hint)
  └─ RetrievalTraversal.traverse(db_path, plan)
       Step 1: exact_sku (if d1_hint)
       Step 2: partial_sku (if d1_hint, needs more)
       Step 3: sibling_traversal (stub, no-op)
       Step 4: lexical_search (if lexical|hybrid)
       Step 5: vector_fallback (if vector|hybrid)
       Step 6: trace_annotation (dedup + annotate)
       → list[CandidateRecord]
  └─ score_candidates(candidates, plan)
       → list[ScoredCandidate] (composite = 0.40s+0.25l+0.15k+0.10r+0.10c)
  └─ dedup_siblings(scored, query_d1, ...)
       D2 routing: sku_match > sku_match_multi > composite_score
       → list[ScoredCandidate] (losers have exclusion_reason="lattice_sibling")
  └─ filter_by_floor(candidates, floor=_RETRIEVAL_FLOOR)
       → selected (composite ≥ 0.35) + excluded
  └─ if selected:
       build_context_packet(trace, selected, limit=10)
       → ContextPacket (is_abstained=False)
     else:
       build_abstained_packet(trace, best_score_seen)
       → ContextPacket (is_abstained=True, selected_memory=[])
```
