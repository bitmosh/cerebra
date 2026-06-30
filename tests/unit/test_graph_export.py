"""Unit tests for cerebra/graph/exporter.py — cerebra/v1 graph export."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

from cerebra.graph.exporter import (
    _d1_category_name,
    _d9_name,
    _d10_name,
    _record_cluster,
    _record_label,
    _record_size,
    _source_cluster,
    _source_size,
    build_graph,
    export_graph,
)
from cerebra.graph.model import ExportStats
from cerebra.storage.migrations import run_migrations

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_vault(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal vault with a migrated database. Returns (vault_path, db_path)."""
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    (vault_path / "data").mkdir()
    (vault_path / "events").mkdir()
    db_path = vault_path / "data" / "cerebra.db"
    run_migrations(db_path)
    return vault_path, db_path


def _insert_source(conn: sqlite3.Connection, source_id: str, canonical_path: str,
                   detected_type: str = "markdown", lifecycle_state: str = "active") -> None:
    conn.execute(
        "INSERT INTO sources (source_id, canonical_path, content_hash, size_bytes, "
        "detected_type, detection_confidence, lifecycle_state, created_at, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (source_id, canonical_path, "abc123", 1024, detected_type, 1.0,
         lifecycle_state, int(time.time()), int(time.time())),
    )


def _insert_document(conn: sqlite3.Connection, document_id: str, source_id: str,
                     title: str = "Test Doc") -> None:
    conn.execute(
        "INSERT INTO documents (document_id, source_id, document_type, title, "
        "lifecycle_state, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (document_id, source_id, "markdown", title, "active", int(time.time())),
    )


def _insert_chunk(conn: sqlite3.Connection, chunk_id: str, document_id: str,
                  source_id: str, heading_path: str = "§1", chunk_index: int = 0,
                  token_estimate: int = 100) -> None:
    conn.execute(
        "INSERT INTO chunks (chunk_id, document_id, source_id, heading_path, chunk_index, "
        "depth, content, content_hash, token_estimate, chunk_strategy, lifecycle_state, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (chunk_id, document_id, source_id, heading_path, chunk_index, 1,
         "Test content", f"hash_{chunk_id}", token_estimate, "heading", "active",
         int(time.time())),
    )


def _insert_record(conn: sqlite3.Connection, record_id: str, source_id: str,
                   chunk_id: str, document_id: str = "doc_001",
                   lifecycle_state: str = "active") -> None:
    conn.execute(
        "INSERT INTO memory_records (record_id, source_id, document_id, chunk_id, content, "
        "content_hash, token_estimate, lifecycle_state, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (record_id, source_id, document_id, chunk_id, "Test content",
         f"hash_{record_id}", 100, lifecycle_state, int(time.time())),
    )


def _insert_sku(conn: sqlite3.Connection, record_id: str, d1: int = 4,
                sku_address: str = "400000.03.00", d9: int = 0,
                d10: int = 0, d1_confidence: float = 0.9) -> None:
    conn.execute(
        "INSERT INTO sku_assignments (assignment_id, record_id, sku_address, d1, d2, d3, "
        "d4, d5, d6, d7, d8, d9, d10, raw_scores_json, d1_confidence, classifier_version, "
        "prompt_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
        "?, ?, ?)",
        (f"asgn_{record_id}", record_id, sku_address, d1, 0, 0, 0, 0, 0, 3, 0, d9, d10,
         '{}', d1_confidence, "v1", "v1", int(time.time())),
    )


# ── Scalar helpers ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestScalarHelpers:
    def test_source_cluster_markdown(self) -> None:
        assert _source_cluster("markdown") == "slate"

    def test_source_cluster_code(self) -> None:
        assert _source_cluster("code") == "gray"

    def test_source_cluster_graph(self) -> None:
        assert _source_cluster("graph") == "teal"

    def test_source_cluster_unknown(self) -> None:
        assert _source_cluster("pdf") == "azure"

    def test_record_cluster_empirical(self) -> None:
        assert _record_cluster(0) == "azure"   # OBSERVATION
        assert _record_cluster(3) == "azure"   # PHENOMENON

    def test_record_cluster_generative(self) -> None:
        assert _record_cluster(4) == "gold"    # TECHNIQUE
        assert _record_cluster(7) == "gold"    # TOOL

    def test_record_cluster_normative(self) -> None:
        assert _record_cluster(8) == "purple"  # PRINCIPLE
        assert _record_cluster(11) == "purple" # CONSTRAINT

    def test_record_cluster_relational(self) -> None:
        assert _record_cluster(12) == "teal"   # EVENT
        assert _record_cluster(15) == "teal"   # RELATION

    def test_source_size_low(self) -> None:
        assert _source_size(0) == 10.0

    def test_source_size_high(self) -> None:
        assert _source_size(100_000) == 24.0

    def test_source_size_mid(self) -> None:
        assert _source_size(5000) == 10.0   # 5000/500=10 exactly

    def test_record_size_low(self) -> None:
        assert _record_size(0) == 4.0

    def test_record_size_high(self) -> None:
        assert _record_size(10_000) == 12.0

    def test_record_label_heading(self) -> None:
        assert _record_label("§1 Overview", "My Doc", "rec_abc") == "§1 Overview"

    def test_record_label_doc_title_fallback(self) -> None:
        assert _record_label(None, "My Doc", "rec_abc") == "My Doc"

    def test_record_label_id_fallback(self) -> None:
        assert _record_label(None, None, "rec_abcdefgh") == "record_rec_abcd"

    def test_d1_category_name_technique(self) -> None:
        assert _d1_category_name(4) == "TECHNIQUE"

    def test_d1_category_name_observation(self) -> None:
        assert _d1_category_name(0) == "OBSERVATION"

    def test_d9_name_text(self) -> None:
        assert _d9_name(0) == "TEXT"

    def test_d10_name_observed(self) -> None:
        assert _d10_name(0) == "OBSERVED"


# ── Empty vault ───────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestEmptyVault:
    def test_empty_vault_graph_shape(self, tmp_path: Path) -> None:
        vault_path, db_path = _make_vault(tmp_path)
        graph = build_graph(db_path, vault_path)
        assert graph["schemaVersion"] == "cerebra/v1"
        assert graph["nodes"] == []
        assert graph["edges"] == []

    def test_empty_vault_stats(self, tmp_path: Path) -> None:
        vault_path, db_path = _make_vault(tmp_path)
        graph = build_graph(db_path, vault_path)
        meta = graph["metadata"]["stats"]
        assert meta["nodeCount"] == 0
        assert meta["edgeCount"] == 0
        assert meta["activeSourceCount"] == 0
        assert meta["activeRecordCount"] == 0

    def test_empty_vault_metadata_fields(self, tmp_path: Path) -> None:
        vault_path, db_path = _make_vault(tmp_path)
        graph = build_graph(db_path, vault_path)
        meta = graph["metadata"]
        assert meta["schemaVersion"] == "cerebra/v1"
        assert "generatedAt" in meta
        assert "cerebraVersion" in meta
        assert str(vault_path) == meta["vaultPath"]


# ── Source nodes ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSourceNodes:
    def test_spine_node_built_for_active_source(self, tmp_path: Path) -> None:
        vault_path, db_path = _make_vault(tmp_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            _insert_source(conn, "src_001", "/vault/notes.md")
        graph = build_graph(db_path, vault_path)
        assert len(graph["nodes"]) == 1
        node = graph["nodes"][0]
        assert node["id"] == "source:src_001"
        assert node["type"] == "spine"
        assert node["label"] == "notes.md"
        assert node["cluster"] == "slate"

    def test_stale_source_excluded(self, tmp_path: Path) -> None:
        vault_path, db_path = _make_vault(tmp_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            _insert_source(conn, "src_001", "/vault/notes.md", lifecycle_state="stale")
        graph = build_graph(db_path, vault_path)
        assert graph["nodes"] == []


# ── Record nodes ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestRecordNodes:
    def _setup(self, tmp_path: Path) -> tuple[Path, Path]:
        vault_path, db_path = _make_vault(tmp_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            _insert_source(conn, "src_001", "/vault/notes.md")
            _insert_document(conn, "doc_001", "src_001", "Notes")
            _insert_chunk(conn, "chk_001", "doc_001", "src_001",
                          heading_path="§1 Intro", chunk_index=0, token_estimate=200)
            _insert_record(conn, "rec_001", "src_001", "chk_001")
            _insert_sku(conn, "rec_001", d1=4, sku_address="400000.03.00")
        return vault_path, db_path

    def test_record_node_built(self, tmp_path: Path) -> None:
        vault_path, db_path = self._setup(tmp_path)
        graph = build_graph(db_path, vault_path)
        ids = {n["id"] for n in graph["nodes"]}
        assert "record:rec_001" in ids

    def test_record_node_fields(self, tmp_path: Path) -> None:
        vault_path, db_path = self._setup(tmp_path)
        graph = build_graph(db_path, vault_path)
        rec_node = next(n for n in graph["nodes"] if n["type"] == "memory_record")
        assert rec_node["cluster"] == "gold"  # d1=4 → Generative
        assert rec_node["raw"]["d1_category"] == "TECHNIQUE"
        assert rec_node["raw"]["d9_modality"] == "TEXT"
        assert rec_node["raw"]["d10_provenance"] == "OBSERVED"
        assert rec_node["raw"]["sku_address"] == "400000.03.00"
        assert rec_node["label"] == "§1 Intro"

    def test_stale_record_excluded(self, tmp_path: Path) -> None:
        vault_path, db_path = _make_vault(tmp_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            _insert_source(conn, "src_001", "/vault/notes.md")
            _insert_document(conn, "doc_001", "src_001")
            _insert_chunk(conn, "chk_001", "doc_001", "src_001")
            _insert_record(conn, "rec_001", "src_001", "chk_001", lifecycle_state="stale")
            _insert_sku(conn, "rec_001")
        graph = build_graph(db_path, vault_path)
        record_nodes = [n for n in graph["nodes"] if n["type"] == "memory_record"]
        assert len(record_nodes) == 0

    def test_unclassified_record_excluded(self, tmp_path: Path) -> None:
        vault_path, db_path = _make_vault(tmp_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            _insert_source(conn, "src_001", "/vault/notes.md")
            _insert_document(conn, "doc_001", "src_001")
            _insert_chunk(conn, "chk_001", "doc_001", "src_001")
            _insert_record(conn, "rec_001", "src_001", "chk_001")
            # no sku_assignment inserted
        graph = build_graph(db_path, vault_path)
        record_nodes = [n for n in graph["nodes"] if n["type"] == "memory_record"]
        assert len(record_nodes) == 0
        assert graph["metadata"]["stats"]["unclassifiedRecordCount"] == 1

    def test_low_confidence_dim_factor(self, tmp_path: Path) -> None:
        vault_path, db_path = _make_vault(tmp_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            _insert_source(conn, "src_001", "/vault/notes.md")
            _insert_document(conn, "doc_001", "src_001")
            _insert_chunk(conn, "chk_001", "doc_001", "src_001")
            _insert_record(conn, "rec_001", "src_001", "chk_001")
            _insert_sku(conn, "rec_001", d1_confidence=0.3)
        graph = build_graph(db_path, vault_path)
        rec_node = next(n for n in graph["nodes"] if n["type"] == "memory_record")
        assert rec_node["raw"]["dimFactor"] == 0.7


# ── Edges ─────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestEdges:
    def _setup_two_adjacent(self, tmp_path: Path) -> tuple[Path, Path]:
        vault_path, db_path = _make_vault(tmp_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            _insert_source(conn, "src_001", "/vault/notes.md")
            _insert_document(conn, "doc_001", "src_001")
            _insert_chunk(conn, "chk_001", "doc_001", "src_001",
                          heading_path="§1", chunk_index=0)
            _insert_chunk(conn, "chk_002", "doc_001", "src_001",
                          heading_path="§2", chunk_index=1)
            _insert_record(conn, "rec_001", "src_001", "chk_001")
            _insert_record(conn, "rec_002", "src_001", "chk_002")
            _insert_sku(conn, "rec_001", d1=4, sku_address="400000.03.00")
            _insert_sku(conn, "rec_002", d1=4, sku_address="400000.03.00")
        return vault_path, db_path

    def test_contains_edges_built(self, tmp_path: Path) -> None:
        vault_path, db_path = self._setup_two_adjacent(tmp_path)
        graph = build_graph(db_path, vault_path)
        contains = [e for e in graph["edges"] if e["type"] == "contains"]
        assert len(contains) == 2
        sources = {e["source"] for e in contains}
        assert sources == {"source:src_001"}

    def test_describes_edge_adjacent(self, tmp_path: Path) -> None:
        vault_path, db_path = self._setup_two_adjacent(tmp_path)
        graph = build_graph(db_path, vault_path)
        describes = [e for e in graph["edges"] if e["type"] == "describes"]
        assert len(describes) == 1
        assert describes[0]["source"] == "record:rec_001"
        assert describes[0]["target"] == "record:rec_002"
        assert describes[0]["bidirectional"] is False

    def test_sku_proximity_same_d1(self, tmp_path: Path) -> None:
        vault_path, db_path = self._setup_two_adjacent(tmp_path)
        graph = build_graph(db_path, vault_path)
        prox = [e for e in graph["edges"] if e["type"] == "sku-proximity"]
        assert len(prox) == 1
        assert prox[0]["bidirectional"] is True

    def test_sku_exact_same_address(self, tmp_path: Path) -> None:
        vault_path, db_path = self._setup_two_adjacent(tmp_path)
        graph = build_graph(db_path, vault_path)
        exact = [e for e in graph["edges"] if e["type"] == "sku-exact"]
        assert len(exact) == 1
        assert exact[0]["weight"] == 0.9

    def test_sku_proximity_cap(self, tmp_path: Path) -> None:
        vault_path, db_path = _make_vault(tmp_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            _insert_source(conn, "src_001", "/vault/notes.md")
            _insert_document(conn, "doc_001", "src_001")
            for i in range(8):
                chunk_id = f"chk_{i:03d}"
                rec_id = f"rec_{i:03d}"
                _insert_chunk(conn, chunk_id, "doc_001", "src_001",
                              heading_path=f"§{i}", chunk_index=i)
                _insert_record(conn, rec_id, "src_001", chunk_id)
                _insert_sku(conn, rec_id, d1=4, sku_address=f"4{i}0000.03.00")
        graph = build_graph(db_path, vault_path)
        prox = [e for e in graph["edges"] if e["type"] == "sku-proximity"]
        # With cap=5, each of 8 nodes can have at most 5 proximity edges
        # Maximum total edges = 8*5/2 = 20, but cap applies per node
        node_counts: dict[str, int] = {}
        for e in prox:
            node_counts[e["source"]] = node_counts.get(e["source"], 0) + 1
            node_counts[e["target"]] = node_counts.get(e["target"], 0) + 1
        for node_id, count in node_counts.items():
            assert count <= 5, f"{node_id} has {count} proximity edges (cap is 5)"


# ── Export function ───────────────────────────────────────────────────────────


@pytest.mark.unit
class TestExportGraph:
    def test_writes_json_file(self, tmp_path: Path) -> None:
        vault_path, _ = _make_vault(tmp_path)
        stats = export_graph(vault_path)
        out = vault_path / ".cerebra" / "graph.json"
        assert out.exists()
        assert stats.out_path == out

    def test_creates_cerebra_dir(self, tmp_path: Path) -> None:
        vault_path, _ = _make_vault(tmp_path)
        cerebra_dir = vault_path / ".cerebra"
        assert not cerebra_dir.exists()
        export_graph(vault_path)
        assert cerebra_dir.exists()

    def test_custom_out_path(self, tmp_path: Path) -> None:
        vault_path, _ = _make_vault(tmp_path)
        out = tmp_path / "custom" / "my-graph.json"
        stats = export_graph(vault_path, out_path=out)
        assert out.exists()
        assert stats.out_path == out

    def test_returns_export_stats(self, tmp_path: Path) -> None:
        vault_path, _ = _make_vault(tmp_path)
        stats = export_graph(vault_path)
        assert isinstance(stats, ExportStats)

    def test_valid_json_output(self, tmp_path: Path) -> None:
        vault_path, _ = _make_vault(tmp_path)
        export_graph(vault_path)
        out = vault_path / ".cerebra" / "graph.json"
        parsed = json.loads(out.read_text())
        assert parsed["schemaVersion"] == "cerebra/v1"
        assert "nodes" in parsed
        assert "edges" in parsed
