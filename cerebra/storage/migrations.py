"""
Forward-only SQLite migration framework.

Each migration is a versioned class that applies one schema change.
Migrations run idempotently: the applied_migrations table tracks what's been run.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from cerebra.storage.db import connect


class Migration(ABC):
    """Base class for all Cerebra migrations."""

    version: int  # must be unique; applied in ascending order
    description: str

    @abstractmethod
    def up(self, conn: sqlite3.Connection) -> None:
        """Apply this migration. Called exactly once per vault."""


class Migration001_InitSchema(Migration):
    """Phase 0: create inspector_events table and migration metadata."""

    version = 1
    description = "Phase 0 initial schema: inspector_events + migration tracking"

    def up(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS applied_migrations (
                version     INTEGER PRIMARY KEY,
                description TEXT    NOT NULL,
                applied_at  INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS inspector_events (
                event_id       TEXT    PRIMARY KEY,
                event_type     TEXT    NOT NULL,
                schema_version INTEGER NOT NULL,
                timestamp      INTEGER NOT NULL,
                session_id     TEXT,
                cycle_id       TEXT,
                step_id        TEXT,
                subject_id     TEXT,
                actor          TEXT    NOT NULL,
                summary        TEXT    NOT NULL,
                data_json      TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_session
                ON inspector_events(session_id);
            CREATE INDEX IF NOT EXISTS idx_events_cycle
                ON inspector_events(cycle_id);
            CREATE INDEX IF NOT EXISTS idx_events_type_time
                ON inspector_events(event_type, timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_subject
                ON inspector_events(subject_id);
            """)


class Migration002_Phase1Schema(Migration):
    """Phase 1: source memory foundation tables.

    One migration per phase discipline: sources, documents, chunks,
    and memory_records all land together here.

    NOTE on source identity: source_id is derived from canonical_path hash.
    A rename creates a new source; the old one goes stale. This is a known
    limitation — path-rename tracking is a Phase 3+ concern.
    """

    version = 2
    description = "Phase 1 source memory: sources, documents, chunks, memory_records"

    def up(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
                source_id           TEXT    PRIMARY KEY,
                canonical_path      TEXT    NOT NULL UNIQUE,
                content_hash        TEXT    NOT NULL,
                size_bytes          INTEGER NOT NULL,
                detected_type       TEXT    NOT NULL,
                detection_confidence REAL   NOT NULL,
                parser_adapter      TEXT,
                parser_version      TEXT,
                chunker_version     TEXT,
                parser_status       TEXT    NOT NULL DEFAULT 'pending',
                lifecycle_state     TEXT    NOT NULL DEFAULT 'active',
                created_at          INTEGER NOT NULL,
                modified_at         INTEGER,
                ingested_at         INTEGER,
                schema_version      INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_sources_path
                ON sources(canonical_path);
            CREATE INDEX IF NOT EXISTS idx_sources_hash
                ON sources(content_hash);
            CREATE INDEX IF NOT EXISTS idx_sources_state
                ON sources(lifecycle_state);

            CREATE TABLE IF NOT EXISTS documents (
                document_id             TEXT    PRIMARY KEY,
                source_id               TEXT    NOT NULL REFERENCES sources(source_id),
                document_type           TEXT    NOT NULL,
                title                   TEXT,
                artifact_path           TEXT,
                normalization_confidence REAL   NOT NULL DEFAULT 1.0,
                parse_warnings_json     TEXT,
                lifecycle_state         TEXT    NOT NULL DEFAULT 'active',
                created_at              INTEGER NOT NULL,
                schema_version          INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_documents_source
                ON documents(source_id);
            CREATE INDEX IF NOT EXISTS idx_documents_state
                ON documents(lifecycle_state);

            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id        TEXT    PRIMARY KEY,
                document_id     TEXT    NOT NULL REFERENCES documents(document_id),
                source_id       TEXT    NOT NULL REFERENCES sources(source_id),
                heading_path    TEXT    NOT NULL DEFAULT '',
                chunk_index     INTEGER NOT NULL,
                depth           INTEGER NOT NULL DEFAULT 0,
                content         TEXT    NOT NULL,
                content_hash    TEXT    NOT NULL,
                token_estimate  INTEGER NOT NULL,
                chunk_strategy  TEXT    NOT NULL,
                lifecycle_state TEXT    NOT NULL DEFAULT 'active',
                created_at      INTEGER NOT NULL,
                schema_version  INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_document
                ON chunks(document_id);
            CREATE INDEX IF NOT EXISTS idx_chunks_source
                ON chunks(source_id);
            CREATE INDEX IF NOT EXISTS idx_chunks_state
                ON chunks(lifecycle_state);

            CREATE TABLE IF NOT EXISTS memory_records (
                record_id       TEXT    PRIMARY KEY,
                record_type     TEXT    NOT NULL DEFAULT 'source_chunk',
                source_id       TEXT    NOT NULL REFERENCES sources(source_id),
                document_id     TEXT    NOT NULL REFERENCES documents(document_id),
                chunk_id        TEXT    NOT NULL REFERENCES chunks(chunk_id),
                content         TEXT    NOT NULL,
                content_hash    TEXT    NOT NULL,
                token_estimate  INTEGER NOT NULL,
                sku_address     TEXT,
                sku_assigned_at INTEGER,
                lifecycle_state TEXT    NOT NULL DEFAULT 'active',
                created_at      INTEGER NOT NULL,
                schema_version  INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_records_chunk
                ON memory_records(chunk_id);
            CREATE INDEX IF NOT EXISTS idx_records_source
                ON memory_records(source_id);
            CREATE INDEX IF NOT EXISTS idx_records_sku
                ON memory_records(sku_address);
            CREATE INDEX IF NOT EXISTS idx_records_state
                ON memory_records(lifecycle_state);
        """)


class Migration003_RenameParseWarnings(Migration):
    """v0.0.1a: rename parse_warnings_json → parse_warnings on documents table.

    The column was shipped as parse_warnings_json in Migration002 but the
    approved spec and all consumer code uses parse_warnings.
    """

    version = 3
    description = "v0.0.1a: rename documents.parse_warnings_json to parse_warnings"

    def up(self, conn: sqlite3.Connection) -> None:
        conn.execute("ALTER TABLE documents RENAME COLUMN parse_warnings_json TO parse_warnings")


class Migration004_SKUAssignments(Migration):
    """Phase 2: sku_assignments table for SKU classifier output.

    Stores full classifier output per memory record including all 16 raw
    category scores, the derived digit values, version metadata, and
    performance telemetry (latency_ms, token counts, model_string).

    D2/D3 intentionally 0x0 ('v1-stub') pending CEREBRA_SKU_SUBCATEGORIES.md.
    subcategory_strategy_version is the reclassification trigger when that
    doc lands.
    """

    version = 4
    description = "Phase 2: sku_assignments table for SKU classifier output"

    def up(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sku_assignments (
                assignment_id               TEXT    PRIMARY KEY,
                record_id                   TEXT    NOT NULL
                    REFERENCES memory_records(record_id),
                sku_address                 TEXT    NOT NULL,
                d1                          INTEGER NOT NULL,
                d2                          INTEGER NOT NULL DEFAULT 0,
                d3                          INTEGER NOT NULL DEFAULT 0,
                d4                          INTEGER NOT NULL DEFAULT 0,
                d5                          INTEGER NOT NULL DEFAULT 0,
                d6                          INTEGER NOT NULL DEFAULT 0,
                d7                          INTEGER NOT NULL,
                d8                          INTEGER NOT NULL,
                d9                          INTEGER NOT NULL,
                d10                         INTEGER NOT NULL DEFAULT 0,
                raw_scores_json             TEXT    NOT NULL,
                d1_confidence               REAL    NOT NULL,
                classifier_version          TEXT    NOT NULL,
                prompt_version              TEXT    NOT NULL,
                subcategory_strategy_version TEXT   NOT NULL DEFAULT 'v1-stub',
                model_string                TEXT,
                latency_ms                  INTEGER,
                input_tokens                INTEGER,
                output_tokens               INTEGER,
                created_at                  INTEGER NOT NULL,
                schema_version              INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_sku_record
                ON sku_assignments(record_id);
            CREATE INDEX IF NOT EXISTS idx_sku_d1
                ON sku_assignments(d1);
            CREATE INDEX IF NOT EXISTS idx_sku_address
                ON sku_assignments(sku_address);
            CREATE INDEX IF NOT EXISTS idx_sku_location
                ON sku_assignments(d1, d2, d3, d4, d5, d6, d9, d10);
        """)


class Migration005_AddPassCount(Migration):
    """v0.1.0: add pass_count column to sku_assignments.

    Defaults to 1 for all existing single-pass assignments.
    Two-pass assignments (PROMPT_VERSION 2.0.0+) will write pass_count=2.
    """

    version = 5
    description = "v0.1.0: add pass_count to sku_assignments"

    def up(self, conn: sqlite3.Connection) -> None:
        # Idempotent: check column existence before adding
        cols = {row[1] for row in conn.execute("PRAGMA table_info(sku_assignments)").fetchall()}
        if "pass_count" not in cols:
            conn.execute(
                "ALTER TABLE sku_assignments ADD COLUMN pass_count INTEGER NOT NULL DEFAULT 1"
            )


class Migration006_Phase3Schema(Migration):
    """Phase 3: storage and index layer — embeddings, graph, freshness tracking.

    Adds five tables per docs/agent/plans/v01_phase3_design.md:

      embeddings        — float32 BLOB per record per model; embedding_alt_*
                          columns reserved for future secondary embeddings
                          (e.g. LoRA training auxiliary). origin_event_id is a
                          soft reference to inspector_events — not a FK because
                          event compaction (CEREBRA_INSPECTOR.md §6.3) must be
                          allowed without cascade issues.

      pending_embeddings — drain queue; decouples slow embedding generation
                           from the ingest pipeline.

      index_state        — one row per index name ('lexical', 'vector', 'graph');
                           tracks last_updated_at and current model version.
                           Populated at vault init, not here.

      graph_nodes        — polymorphic node table with node_type discriminator.
                           entity_id/entity_table are soft FKs (SQLite has no
                           polymorphic FK support). updated_at is application-
                           maintained — no trigger, by design (triggers fire
                           silently without inspector events).

      graph_edges        — polymorphic edge table. ON DELETE RESTRICT on both
                           node FKs: graph cleanup is lifecycle-state-driven;
                           hard-deleting a node that still has edges is a bug,
                           not a supported operation.
    """

    version = 6
    description = "Phase 3: embeddings, pending_embeddings, index_state, graph_nodes, graph_edges"

    def up(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS embeddings (
                embedding_id        TEXT    PRIMARY KEY,
                record_id           TEXT    NOT NULL
                    REFERENCES memory_records(record_id),
                embedding_model     TEXT    NOT NULL,
                model_version       TEXT    NOT NULL,
                vector_bytes        BLOB    NOT NULL,
                dimensions          INTEGER NOT NULL,
                embedding_alt       BLOB    NULL,
                embedding_alt_model TEXT    NULL,
                embedding_alt_dim   INTEGER NULL,
                created_at          INTEGER NOT NULL,
                schema_version      INTEGER NOT NULL DEFAULT 1,
                UNIQUE (record_id, embedding_model, model_version)
            );

            CREATE INDEX IF NOT EXISTS idx_emb_record
                ON embeddings(record_id);
            CREATE INDEX IF NOT EXISTS idx_emb_model
                ON embeddings(embedding_model, model_version);

            CREATE TABLE IF NOT EXISTS pending_embeddings (
                record_id   TEXT    PRIMARY KEY
                    REFERENCES memory_records(record_id),
                queued_at   INTEGER NOT NULL,
                attempt     INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS index_state (
                index_name      TEXT    PRIMARY KEY,
                last_updated_at INTEGER NOT NULL,
                record_count    INTEGER NOT NULL DEFAULT 0,
                model_name      TEXT,
                model_version   TEXT,
                is_building     INTEGER NOT NULL DEFAULT 0,
                schema_version  INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS graph_nodes (
                node_id         TEXT    PRIMARY KEY,
                node_type       TEXT    NOT NULL,
                label           TEXT    NOT NULL,
                entity_id       TEXT,
                entity_table    TEXT,
                sku_address     TEXT,
                lifecycle_state TEXT    NOT NULL DEFAULT 'active',
                origin_event_id TEXT,
                payload_json    TEXT    NOT NULL DEFAULT '{}',
                created_at      INTEGER NOT NULL,
                updated_at      INTEGER NOT NULL,
                schema_version  INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_gn_entity
                ON graph_nodes(entity_id, entity_table);
            CREATE INDEX IF NOT EXISTS idx_gn_type
                ON graph_nodes(node_type);
            CREATE INDEX IF NOT EXISTS idx_gn_type_state
                ON graph_nodes(node_type, lifecycle_state);
            CREATE INDEX IF NOT EXISTS idx_gn_sku
                ON graph_nodes(sku_address);
            CREATE INDEX IF NOT EXISTS idx_gn_state
                ON graph_nodes(lifecycle_state);
            CREATE INDEX IF NOT EXISTS idx_gn_created
                ON graph_nodes(created_at);

            CREATE TABLE IF NOT EXISTS graph_edges (
                edge_id         TEXT    PRIMARY KEY,
                edge_type       TEXT    NOT NULL,
                source_node_id  TEXT    NOT NULL
                    REFERENCES graph_nodes(node_id) ON DELETE RESTRICT,
                target_node_id  TEXT    NOT NULL
                    REFERENCES graph_nodes(node_id) ON DELETE RESTRICT,
                confidence      REAL    NOT NULL DEFAULT 1.0,
                weight          REAL    NOT NULL DEFAULT 1.0,
                evidence        TEXT,
                created_by      TEXT    NOT NULL,
                origin_event_id TEXT,
                lifecycle_state TEXT    NOT NULL DEFAULT 'active',
                payload_json    TEXT    NOT NULL DEFAULT '{}',
                created_at      INTEGER NOT NULL,
                updated_at      INTEGER NOT NULL,
                schema_version  INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_ge_source
                ON graph_edges(source_node_id, edge_type, lifecycle_state);
            CREATE INDEX IF NOT EXISTS idx_ge_target
                ON graph_edges(target_node_id, edge_type, lifecycle_state);
            CREATE INDEX IF NOT EXISTS idx_ge_type
                ON graph_edges(edge_type, lifecycle_state);
            CREATE INDEX IF NOT EXISTS idx_ge_sibling
                ON graph_edges(source_node_id, target_node_id);
            CREATE INDEX IF NOT EXISTS idx_ge_created
                ON graph_edges(created_at);
        """)


class Migration007_SeedIndexStateAndQueue(Migration):
    """Backfill migration for vaults that had Migration006 applied before seeding was added.

    Migration006 created the schema but did not seed index_state or queue existing
    memory_records into pending_embeddings. This migration does both idempotently so
    that fresh vaults and already-partially-backfilled vaults converge to the same state.
    """

    version = 7
    description = "Phase 3 backfill: seed index_state, queue active records for embedding"

    def up(self, conn: sqlite3.Connection) -> None:
        # Seed the three named indexes. INSERT OR IGNORE is idempotent.
        conn.executemany(
            "INSERT OR IGNORE INTO index_state (index_name, last_updated_at) VALUES (?, 0)",
            [("lexical",), ("vector",), ("graph",)],
        )
        # Queue all currently active memory_records for their first embedding pass.
        # INSERT OR IGNORE skips records already in the queue (e.g. from a prior manual backfill).
        conn.execute(
            "INSERT OR IGNORE INTO pending_embeddings (record_id, queued_at, attempt)"
            " SELECT record_id, CAST(strftime('%s','now') AS INTEGER), 0"
            " FROM memory_records WHERE lifecycle_state = 'active'"
        )


class Migration008_RetrievalTraces(Migration):
    """Phase 4: retrieval trace tables for inspectable query audit trails.

    Three tables per docs/agent/plans/v01_phase4_design.md §6:

      retrieval_traces      — one row per query attempt; links to the resulting
                              ContextPacket (or null on abstention).

      retrieval_steps       — one row per traversal step (steps 1–6); tracks
                              candidate counts, timing, and skip reasons.
                              step_name values: query_sku_construction,
                              exact_sku, partial_sku, sibling_traversal,
                              vector_fallback, trace_annotation.

      retrieval_candidates  — one row per candidate surfaced; records which
                              step found it, the full CompositeScore JSON,
                              whether it was selected, and the exclusion
                              reason if not. Enables "why was this retrieved"
                              and "why was this excluded" inspector queries.

    Retention: indefinite in v0.1.x. Pruning command deferred to Phase 5+.
    """

    version = 8
    description = "Phase 4: retrieval_traces, retrieval_steps, retrieval_candidates"

    def up(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS retrieval_traces (
                trace_id          TEXT    PRIMARY KEY,
                query             TEXT    NOT NULL,
                mode              TEXT    NOT NULL,
                query_sku_d1      INTEGER,
                query_sku_pattern TEXT,
                plan_json         TEXT    NOT NULL DEFAULT '{}',
                started_at        INTEGER NOT NULL,
                finished_at       INTEGER NOT NULL,
                duration_ms       INTEGER NOT NULL,
                candidate_count   INTEGER NOT NULL DEFAULT 0,
                selected_count    INTEGER NOT NULL DEFAULT 0,
                abstained         INTEGER NOT NULL DEFAULT 0,
                context_packet_id TEXT,
                schema_version    INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_trace_started
                ON retrieval_traces(started_at);
            CREATE INDEX IF NOT EXISTS idx_trace_mode
                ON retrieval_traces(mode);
            CREATE INDEX IF NOT EXISTS idx_trace_abstained
                ON retrieval_traces(abstained);

            CREATE TABLE IF NOT EXISTS retrieval_steps (
                step_id          TEXT    PRIMARY KEY,
                trace_id         TEXT    NOT NULL
                    REFERENCES retrieval_traces(trace_id),
                step_number      INTEGER NOT NULL,
                step_name        TEXT    NOT NULL,
                candidate_count  INTEGER NOT NULL DEFAULT 0,
                new_candidates   INTEGER NOT NULL DEFAULT 0,
                duration_ms      INTEGER NOT NULL DEFAULT 0,
                skipped          INTEGER NOT NULL DEFAULT 0,
                skip_reason      TEXT,
                schema_version   INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_step_trace
                ON retrieval_steps(trace_id, step_number);

            CREATE TABLE IF NOT EXISTS retrieval_candidates (
                candidate_id     TEXT    PRIMARY KEY,
                trace_id         TEXT    NOT NULL
                    REFERENCES retrieval_traces(trace_id),
                record_id        TEXT    NOT NULL,
                step_surfaced    TEXT    NOT NULL,
                retrieval_path   TEXT    NOT NULL,
                salience_score   REAL    NOT NULL,
                score_json       TEXT    NOT NULL DEFAULT '{}',
                selected         INTEGER NOT NULL DEFAULT 0,
                rank             INTEGER,
                exclusion_reason TEXT,
                schema_version   INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_cand_trace
                ON retrieval_candidates(trace_id, selected);
            CREATE INDEX IF NOT EXISTS idx_cand_record
                ON retrieval_candidates(record_id);
        """)


class Migration009_Phase5Schema(Migration):
    """Phase 5: session management, working memory, and truth tower tables.

    Three new tables: sessions, working_memory_items, truth_tower_items.
    All FK constraints use ON DELETE RESTRICT — cleanup is lifecycle-state-driven
    (evicted_at, status='closed'), never hard-delete.

    Forward-only invariant: if a later issue surfaces with this schema,
    Migration010 addresses it; do not edit Migration009 in place after it
    applies anywhere.
    """

    version = 9
    description = "Phase 5 working memory and truth tower: sessions, working_memory_items, truth_tower_items"

    def up(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id       TEXT    PRIMARY KEY,
                vault_path       TEXT    NOT NULL,
                status           TEXT    NOT NULL DEFAULT 'active'
                                         CHECK (status IN ('active', 'closed')),
                started_at       INTEGER NOT NULL,
                last_active_at   INTEGER NOT NULL,
                schema_version   INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_vault_status
                ON sessions(vault_path, status);

            CREATE TABLE IF NOT EXISTS working_memory_items (
                item_id             TEXT    PRIMARY KEY,
                session_id          TEXT    NOT NULL
                                            REFERENCES sessions(session_id)
                                                ON DELETE RESTRICT,
                slot_type           TEXT    NOT NULL
                                            CHECK (slot_type IN (
                                                'goal', 'constraint', 'context', 'hypothesis',
                                                'evidence', 'contradiction', 'recent_output',
                                                'question', 'procedure', 'interrupt'
                                            )),
                record_id           TEXT    REFERENCES memory_records(record_id)
                                                ON DELETE RESTRICT,
                content_summary     TEXT    NOT NULL,
                salience_score      REAL    NOT NULL DEFAULT 0.0,
                is_pinned           INTEGER NOT NULL DEFAULT 0,
                promoted_at         INTEGER NOT NULL,
                evicted_at          INTEGER,
                schema_version      INTEGER NOT NULL DEFAULT 1,
                interpretive_lens   TEXT,
                frame_metadata_json TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_wmi_session_slot
                ON working_memory_items(session_id, slot_type)
                WHERE evicted_at IS NULL;

            CREATE INDEX IF NOT EXISTS idx_wmi_session_active
                ON working_memory_items(session_id)
                WHERE evicted_at IS NULL;

            CREATE TABLE IF NOT EXISTS truth_tower_items (
                tower_item_id       TEXT    PRIMARY KEY,
                session_id          TEXT    NOT NULL
                                            REFERENCES sessions(session_id)
                                                ON DELETE RESTRICT,
                tier                INTEGER NOT NULL CHECK (tier IN (1, 2)),
                wm_item_id          TEXT    REFERENCES working_memory_items(item_id)
                                                ON DELETE RESTRICT,
                record_id           TEXT    REFERENCES memory_records(record_id)
                                                ON DELETE RESTRICT,
                retrieval_trace_id  TEXT    REFERENCES retrieval_traces(trace_id)
                                                ON DELETE RESTRICT,
                content_summary     TEXT    NOT NULL,
                salience_score      REAL    NOT NULL,
                sku_address         TEXT,
                t1_citation_id      TEXT    REFERENCES truth_tower_items(tower_item_id)
                                                ON DELETE RESTRICT,
                is_pinned           INTEGER NOT NULL DEFAULT 0,
                is_stale            INTEGER NOT NULL DEFAULT 0,
                promoted_at         INTEGER NOT NULL,
                evicted_at          INTEGER,
                schema_version      INTEGER NOT NULL DEFAULT 1,
                CHECK ((tier = 1 AND t1_citation_id IS NULL) OR (tier = 2 AND t1_citation_id IS NOT NULL))
            );

            CREATE INDEX IF NOT EXISTS idx_tti_session_tier
                ON truth_tower_items(session_id, tier)
                WHERE evicted_at IS NULL;

            CREATE INDEX IF NOT EXISTS idx_tti_t1_citation
                ON truth_tower_items(t1_citation_id)
                WHERE evicted_at IS NULL;
        """)


class Migration010_LatticeColumns(Migration):
    """Interpretive lattice Phase 1: sibling lineage columns on memory_records.

    Three new columns (all nullable / defaulting to 0):

      lattice_lineage_id TEXT    — shared ID linking sibling records from the same chunk.
                                   NULL for single-commit records.
      is_lattice_member  INTEGER — 0 for normal records, 1 for any lattice sibling
                                   (including the primary when multi-committed).
      lattice_confidence REAL    — per-sibling classifier confidence for its category.
                                   NULL for non-lattice records.

    SQLite ALTER TABLE supports ADD COLUMN without a full table rebuild; the
    DEFAULT value is applied immediately to all existing rows at the storage
    layer without a table scan (SQLite evaluates the default on read when the
    column is absent from the stored row).

    Existing 745+ records are unaffected — they keep is_lattice_member = 0
    and NULL for the other two columns.
    """

    version = 10
    description = "Interpretive lattice Phase 1: lattice_lineage_id, is_lattice_member, lattice_confidence"

    def up(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            ALTER TABLE memory_records ADD COLUMN lattice_lineage_id TEXT;
            ALTER TABLE memory_records ADD COLUMN is_lattice_member INTEGER NOT NULL DEFAULT 0;
            ALTER TABLE memory_records ADD COLUMN lattice_confidence REAL;

            CREATE INDEX IF NOT EXISTS idx_records_lattice_lineage
                ON memory_records(lattice_lineage_id)
                WHERE lattice_lineage_id IS NOT NULL;
        """)


class Migration011_LatticeRetrieval(Migration):
    """Lattice Step 2: lattice dedup columns on retrieval_candidates.

    Three new columns (all nullable):
      lattice_sibling_count   INTEGER DEFAULT 0  — total siblings in the lineage group
                                                   (0 = not a lattice candidate)
      lattice_winner_record_id TEXT              — record_id of the winning sibling
                                                   NULL for non-lattice candidates
      lattice_routing_basis   TEXT               — how the winner was chosen:
                                                   sku_match | sku_match_multi |
                                                   composite_score | earliest_promotion
                                                   NULL for non-lattice candidates

    A partial index on lattice_winner_record_id speeds up post-dedup lookups
    on groups that were actually resolved (sibling_count > 0).
    """

    version = 11
    description = "Lattice Step 2: lattice_sibling_count, lattice_winner_record_id, lattice_routing_basis on retrieval_candidates"

    def up(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            ALTER TABLE retrieval_candidates ADD COLUMN lattice_sibling_count INTEGER NOT NULL DEFAULT 0;
            ALTER TABLE retrieval_candidates ADD COLUMN lattice_winner_record_id TEXT;
            ALTER TABLE retrieval_candidates ADD COLUMN lattice_routing_basis TEXT;

            CREATE INDEX IF NOT EXISTS idx_rc_lattice_winner
                ON retrieval_candidates(lattice_winner_record_id)
                WHERE lattice_sibling_count > 0;
        """)


class Migration012_Evaluations(Migration):
    """Phase 6 Step 2: evaluations table for composed signal evaluation packets.

    Predictions and outcomes tables land in Migration013 (Phase 6 Step 3).
    """

    version = 12
    description = "Phase 6 Step 2: evaluations table"

    def up(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS evaluations (
                evaluation_id           TEXT    PRIMARY KEY,
                session_id              TEXT    NOT NULL,
                cycle_id                TEXT    NOT NULL,
                step_id                 TEXT    NOT NULL,
                composite_score         REAL    NOT NULL,
                per_signal_scores       TEXT    NOT NULL,
                weights_used            TEXT    NOT NULL,
                composite_floor_violated INTEGER NOT NULL,
                confidence              REAL,
                composed_at             INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_evaluations_session
                ON evaluations(session_id);
            CREATE INDEX IF NOT EXISTS idx_evaluations_cycle
                ON evaluations(cycle_id);
        """)


# Registry: all migrations in ascending version order.
ALL_MIGRATIONS: list[Migration] = [
    Migration001_InitSchema(),
    Migration002_Phase1Schema(),
    Migration003_RenameParseWarnings(),
    Migration004_SKUAssignments(),
    Migration005_AddPassCount(),
    Migration006_Phase3Schema(),
    Migration007_SeedIndexStateAndQueue(),
    Migration008_RetrievalTraces(),
    Migration009_Phase5Schema(),
    Migration010_LatticeColumns(),
    Migration011_LatticeRetrieval(),
    Migration012_Evaluations(),
]


def run_migrations(db_path: Path) -> list[int]:
    """
    Apply all pending migrations to the database at db_path.
    Returns list of version numbers that were applied this run.
    """
    import time

    conn = connect(db_path)
    try:
        # Bootstrap: ensure applied_migrations table exists before any query
        conn.execute("""
            CREATE TABLE IF NOT EXISTS applied_migrations (
                version     INTEGER PRIMARY KEY,
                description TEXT    NOT NULL,
                applied_at  INTEGER NOT NULL
            )
            """)
        conn.commit()

        applied = {
            row[0] for row in conn.execute("SELECT version FROM applied_migrations").fetchall()
        }

        newly_applied: list[int] = []
        for migration in ALL_MIGRATIONS:
            if migration.version in applied:
                continue
            migration.up(conn)
            conn.execute(
                "INSERT INTO applied_migrations (version, description, applied_at) VALUES (?, ?, ?)",
                (migration.version, migration.description, int(time.time())),
            )
            conn.commit()
            newly_applied.append(migration.version)

        return newly_applied
    finally:
        conn.close()
