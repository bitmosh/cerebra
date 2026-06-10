"""Unit tests for cerebra/storage/graph_store.py."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import json

from cerebra.inspector.sqlite_log import SQLiteEventLog
from cerebra.storage.graph_store import (
    get_1hop,
    get_edge,
    get_neighbors,
    get_node,
    get_node_for_entity,
    get_sibling_targets,
    make_edge_id,
    make_node_id,
    set_edge_lifecycle,
    set_node_lifecycle,
    upsert_edge,
    upsert_node,
    walk_parent_chain,
)
from cerebra.storage.migrations import run_migrations


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path: Path) -> Path:
    """Fresh migrated database per test."""
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    return db_path


def _node(
    node_id: str,
    *,
    node_type: str = "Source",
    label: str = "test",
    lifecycle_state: str = "active",
    entity_id: str | None = None,
    entity_table: str | None = None,
) -> dict:
    return {
        "node_id": node_id,
        "node_type": node_type,
        "label": label,
        "lifecycle_state": lifecycle_state,
        "entity_id": entity_id,
        "entity_table": entity_table,
        "payload_json": "{}",
        "created_at": 1000,
        "updated_at": 1000,
    }


def _edge(
    edge_id: str,
    source: str,
    target: str,
    *,
    edge_type: str = "CONTAINS",
    lifecycle_state: str = "active",
    confidence: float = 1.0,
    weight: float = 1.0,
) -> dict:
    return {
        "edge_id": edge_id,
        "edge_type": edge_type,
        "source_node_id": source,
        "target_node_id": target,
        "confidence": confidence,
        "weight": weight,
        "created_by": "test",
        "lifecycle_state": lifecycle_state,
        "payload_json": "{}",
        "created_at": 1000,
        "updated_at": 1000,
    }


# ── ID generation ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestIdGeneration:
    def test_make_node_id_is_deterministic(self) -> None:
        assert make_node_id("sources:abc") == make_node_id("sources:abc")

    def test_make_node_id_prefix(self) -> None:
        assert make_node_id("sources:abc").startswith("gn_")

    def test_make_node_id_different_keys_differ(self) -> None:
        assert make_node_id("sources:abc") != make_node_id("sources:xyz")

    def test_make_edge_id_prefix(self) -> None:
        assert make_edge_id().startswith("ge_")

    def test_make_edge_id_is_random(self) -> None:
        assert make_edge_id() != make_edge_id()


# ── Node CRUD ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestNodeCrud:
    def test_upsert_returns_node_id(self, db: Path) -> None:
        result = upsert_node(db, _node("gn_001"))
        assert result == "gn_001"

    def test_get_node_round_trip(self, db: Path) -> None:
        upsert_node(db, _node("gn_001", label="hello", node_type="Document"))
        node = get_node(db, "gn_001")
        assert node is not None
        assert node["label"] == "hello"
        assert node["node_type"] == "Document"

    def test_get_node_missing_returns_none(self, db: Path) -> None:
        assert get_node(db, "gn_nope") is None

    def test_upsert_updates_mutable_fields(self, db: Path) -> None:
        upsert_node(db, _node("gn_001", label="old", lifecycle_state="active"))
        upsert_node(db, _node("gn_001", label="new", lifecycle_state="archived"))
        node = get_node(db, "gn_001")
        assert node is not None
        assert node["label"] == "new"
        assert node["lifecycle_state"] == "archived"

    def test_upsert_preserves_created_at(self, db: Path) -> None:
        first = _node("gn_001")
        first["created_at"] = 500
        upsert_node(db, first)
        second = _node("gn_001")
        second["created_at"] = 9999
        second["updated_at"] = 9999
        upsert_node(db, second)
        node = get_node(db, "gn_001")
        assert node is not None
        assert node["created_at"] == 500  # immutable on conflict

    def test_upsert_preserves_node_type(self, db: Path) -> None:
        upsert_node(db, _node("gn_001", node_type="Source"))
        upsert_node(db, _node("gn_001", node_type="Document"))  # attempt overwrite
        node = get_node(db, "gn_001")
        assert node is not None
        assert node["node_type"] == "Source"  # immutable

    def test_get_node_for_entity(self, db: Path) -> None:
        upsert_node(db, _node("gn_001", entity_id="src_123", entity_table="sources"))
        node = get_node_for_entity(db, "src_123", "sources")
        assert node is not None
        assert node["node_id"] == "gn_001"

    def test_get_node_for_entity_missing(self, db: Path) -> None:
        assert get_node_for_entity(db, "src_nope", "sources") is None

    def test_get_node_for_entity_table_discriminates(self, db: Path) -> None:
        upsert_node(db, _node("gn_001", entity_id="doc_123", entity_table="documents"))
        assert get_node_for_entity(db, "doc_123", "sources") is None
        assert get_node_for_entity(db, "doc_123", "documents") is not None

    def test_set_node_lifecycle(self, db: Path) -> None:
        upsert_node(db, _node("gn_001", lifecycle_state="active"))
        set_node_lifecycle(db, "gn_001", "tombstoned")
        node = get_node(db, "gn_001")
        assert node is not None
        assert node["lifecycle_state"] == "tombstoned"
        assert node["updated_at"] > 1000  # updated_at was stamped

    def test_set_node_lifecycle_emits_event(self, db: Path) -> None:
        log = SQLiteEventLog(db)
        upsert_node(db, _node("gn_001", lifecycle_state="active"))
        set_node_lifecycle(db, "gn_001", "archived", event_log=log)
        events = log.query_by_type("GraphNodeLifecycleChanged")
        assert len(events) == 1
        data = json.loads(events[0]["data_json"])
        assert data["node_id"] == "gn_001"
        assert data["new_state"] == "archived"

    def test_set_node_lifecycle_no_event_without_log(self, db: Path) -> None:
        upsert_node(db, _node("gn_001", lifecycle_state="active"))
        set_node_lifecycle(db, "gn_001", "tombstoned")  # no event_log — should not raise
        node = get_node(db, "gn_001")
        assert node is not None
        assert node["lifecycle_state"] == "tombstoned"


# ── Edge CRUD ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestEdgeCrud:
    def _make_two_nodes(self, db: Path) -> tuple[str, str]:
        upsert_node(db, _node("gn_src"))
        upsert_node(db, _node("gn_doc", node_type="Document"))
        return "gn_src", "gn_doc"

    def test_upsert_returns_edge_id(self, db: Path) -> None:
        src, tgt = self._make_two_nodes(db)
        result = upsert_edge(db, _edge("ge_001", src, tgt))
        assert result == "ge_001"

    def test_get_edge_round_trip(self, db: Path) -> None:
        src, tgt = self._make_two_nodes(db)
        upsert_edge(db, _edge("ge_001", src, tgt, edge_type="CONTAINS", confidence=0.9))
        edge = get_edge(db, "ge_001")
        assert edge is not None
        assert edge["edge_type"] == "CONTAINS"
        assert edge["confidence"] == pytest.approx(0.9)

    def test_get_edge_missing_returns_none(self, db: Path) -> None:
        assert get_edge(db, "ge_nope") is None

    def test_upsert_edge_updates_mutable_fields(self, db: Path) -> None:
        src, tgt = self._make_two_nodes(db)
        upsert_edge(db, _edge("ge_001", src, tgt, confidence=0.5, weight=0.5))
        upsert_edge(db, _edge("ge_001", src, tgt, confidence=0.9, weight=0.9))
        edge = get_edge(db, "ge_001")
        assert edge is not None
        assert edge["confidence"] == pytest.approx(0.9)
        assert edge["weight"] == pytest.approx(0.9)

    def test_upsert_edge_preserves_created_at(self, db: Path) -> None:
        src, tgt = self._make_two_nodes(db)
        e1 = _edge("ge_001", src, tgt)
        e1["created_at"] = 500
        upsert_edge(db, e1)
        e2 = _edge("ge_001", src, tgt)
        e2["created_at"] = 9999
        upsert_edge(db, e2)
        edge = get_edge(db, "ge_001")
        assert edge is not None
        assert edge["created_at"] == 500  # immutable

    def test_set_edge_lifecycle(self, db: Path) -> None:
        src, tgt = self._make_two_nodes(db)
        upsert_edge(db, _edge("ge_001", src, tgt))
        set_edge_lifecycle(db, "ge_001", "archived")
        edge = get_edge(db, "ge_001")
        assert edge is not None
        assert edge["lifecycle_state"] == "archived"
        assert edge["updated_at"] > 1000

    def test_set_edge_lifecycle_emits_event(self, db: Path) -> None:
        log = SQLiteEventLog(db)
        src, tgt = self._make_two_nodes(db)
        upsert_edge(db, _edge("ge_001", src, tgt))
        set_edge_lifecycle(db, "ge_001", "tombstoned", event_log=log)
        events = log.query_by_type("GraphEdgeLifecycleChanged")
        assert len(events) == 1
        data = json.loads(events[0]["data_json"])
        assert data["edge_id"] == "ge_001"
        assert data["new_state"] == "tombstoned"

    def test_set_edge_lifecycle_no_event_without_log(self, db: Path) -> None:
        src, tgt = self._make_two_nodes(db)
        upsert_edge(db, _edge("ge_001", src, tgt))
        set_edge_lifecycle(db, "ge_001", "archived")  # no event_log — should not raise
        edge = get_edge(db, "ge_001")
        assert edge is not None
        assert edge["lifecycle_state"] == "archived"

    def test_edge_requires_existing_source_node(self, db: Path) -> None:
        upsert_node(db, _node("gn_doc", node_type="Document"))
        import sqlite3
        with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError)):
            upsert_edge(db, _edge("ge_001", "gn_nonexistent", "gn_doc"))

    def test_edge_requires_existing_target_node(self, db: Path) -> None:
        upsert_node(db, _node("gn_src"))
        import sqlite3
        with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError)):
            upsert_edge(db, _edge("ge_001", "gn_src", "gn_nonexistent"))


# ── Traversal ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestTraversal:
    def _build_chain(self, db: Path) -> tuple[str, str, str]:
        """source → document (CONTAINS) → chunk (DERIVED_FROM)."""
        upsert_node(db, _node("gn_src", node_type="Source", label="src"))
        upsert_node(db, _node("gn_doc", node_type="Document", label="doc"))
        upsert_node(db, _node("gn_chk", node_type="Chunk", label="chk"))
        # src CONTAINS doc
        upsert_edge(db, _edge("ge_1", "gn_src", "gn_doc", edge_type="CONTAINS"))
        # chk DERIVED_FROM doc
        upsert_edge(db, _edge("ge_2", "gn_chk", "gn_doc", edge_type="DERIVED_FROM"))
        return "gn_src", "gn_doc", "gn_chk"

    def test_get_neighbors_outbound(self, db: Path) -> None:
        src, doc, chk = self._build_chain(db)
        neighbors = get_neighbors(db, src, direction="outbound")
        ids = {n["node_id"] for n in neighbors}
        assert ids == {"gn_doc"}

    def test_get_neighbors_inbound(self, db: Path) -> None:
        src, doc, chk = self._build_chain(db)
        # gn_doc is the target of both gn_src→gn_doc (CONTAINS) and gn_chk→gn_doc (DERIVED_FROM)
        neighbors = get_neighbors(db, doc, direction="inbound")
        ids = {n["node_id"] for n in neighbors}
        assert ids == {"gn_src", "gn_chk"}

    def test_get_neighbors_both(self, db: Path) -> None:
        src, doc, chk = self._build_chain(db)
        # gn_doc: inbound from gn_src, outbound has none; gn_chk derives FROM gn_doc
        # so gn_doc inbound = [gn_src], outbound = [] (no edge from gn_doc)
        # gn_chk outbound = [gn_doc]
        neighbors = get_neighbors(db, doc, direction="both")
        ids = {n["node_id"] for n in neighbors}
        assert "gn_src" in ids  # inbound
        # gn_chk connects TO gn_doc (gn_chk → gn_doc), so gn_doc inbound also includes gn_chk
        assert "gn_chk" in ids

    def test_get_neighbors_edge_type_filter(self, db: Path) -> None:
        src, doc, chk = self._build_chain(db)
        # gn_chk has outbound DERIVED_FROM to gn_doc; filter for CONTAINS should return []
        neighbors = get_neighbors(db, chk, direction="outbound", edge_type="CONTAINS")
        assert neighbors == []
        neighbors = get_neighbors(db, chk, direction="outbound", edge_type="DERIVED_FROM")
        assert len(neighbors) == 1
        assert neighbors[0]["node_id"] == "gn_doc"

    def test_get_neighbors_skips_archived_edges(self, db: Path) -> None:
        src, doc, chk = self._build_chain(db)
        set_edge_lifecycle(db, "ge_1", "archived")
        neighbors = get_neighbors(db, src, direction="outbound")
        # ge_1 archived → gn_doc should not appear
        assert neighbors == []

    def test_get_neighbors_skips_archived_nodes(self, db: Path) -> None:
        src, doc, chk = self._build_chain(db)
        set_node_lifecycle(db, doc, "archived")
        neighbors = get_neighbors(db, src, direction="outbound")
        assert neighbors == []

    def test_get_neighbors_invalid_direction(self, db: Path) -> None:
        with pytest.raises(ValueError, match="direction"):
            get_neighbors(db, "gn_any", direction="sideways")

    def test_get_1hop_keys(self, db: Path) -> None:
        src, doc, chk = self._build_chain(db)
        hop = get_1hop(db, src)
        assert "outbound" in hop
        assert "inbound" in hop
        assert hop["outbound"][0]["node_id"] == "gn_doc"
        assert hop["inbound"] == []

    def test_get_sibling_targets(self, db: Path) -> None:
        # gn_src has one outbound target: gn_doc
        src, doc, chk = self._build_chain(db)
        targets = get_sibling_targets(db, src)
        assert targets == ["gn_doc"]

    def test_get_sibling_targets_empty(self, db: Path) -> None:
        src, doc, chk = self._build_chain(db)
        # gn_doc has no outbound edges
        targets = get_sibling_targets(db, doc)
        assert targets == []

    def test_get_sibling_targets_respects_lifecycle(self, db: Path) -> None:
        src, doc, chk = self._build_chain(db)
        set_edge_lifecycle(db, "ge_1", "archived")
        assert get_sibling_targets(db, src) == []

    def test_walk_parent_chain_via_contains_inbound(self, db: Path) -> None:
        # gn_src CONTAINS gn_doc: walking from gn_doc should find gn_src
        src, doc, chk = self._build_chain(db)
        chain = walk_parent_chain(db, doc)
        ids = [n["node_id"] for n in chain]
        assert src in ids

    def test_walk_parent_chain_via_derived_from_outbound(self, db: Path) -> None:
        # gn_chk DERIVED_FROM gn_doc: walking from gn_chk should find gn_doc
        src, doc, chk = self._build_chain(db)
        chain = walk_parent_chain(db, chk)
        ids = [n["node_id"] for n in chain]
        assert doc in ids

    def test_walk_parent_chain_deep(self, db: Path) -> None:
        # chk → doc (DERIVED_FROM) + src → doc (CONTAINS): walking from chk should
        # eventually surface gn_src too (via doc → src via CONTAINS inbound)
        src, doc, chk = self._build_chain(db)
        chain = walk_parent_chain(db, chk)
        ids = {n["node_id"] for n in chain}
        assert doc in ids
        assert src in ids

    def test_walk_parent_chain_excludes_start_node(self, db: Path) -> None:
        src, doc, chk = self._build_chain(db)
        chain = walk_parent_chain(db, chk)
        ids = [n["node_id"] for n in chain]
        assert chk not in ids

    def test_walk_parent_chain_empty_for_root(self, db: Path) -> None:
        # gn_src has no parents (nothing points to it via parent-type edges)
        src, doc, chk = self._build_chain(db)
        chain = walk_parent_chain(db, src)
        assert chain == []

    def test_walk_parent_chain_respects_max_depth(self, db: Path) -> None:
        # Build a linear chain of 5 nodes: n0→n1→n2→n3→n4 via DERIVED_FROM
        for i in range(5):
            upsert_node(db, _node(f"gn_d{i}", label=f"n{i}"))
        for i in range(4):
            upsert_edge(
                db,
                _edge(f"ge_d{i}", f"gn_d{i}", f"gn_d{i+1}", edge_type="DERIVED_FROM"),
            )
        # max_depth=2 from gn_d0 should return at most 2 levels: gn_d1, gn_d2
        chain = walk_parent_chain(db, "gn_d0", max_depth=2)
        assert len(chain) <= 2

    def test_get_neighbors_both_deduplicates(self, db: Path) -> None:
        # If a node is both an outbound and inbound neighbor (self-loop prevented by
        # schema, so test with two edges from different types pointing to same node)
        upsert_node(db, _node("gn_a"))
        upsert_node(db, _node("gn_b"))
        upsert_edge(db, _edge("ge_ab1", "gn_a", "gn_b", edge_type="CONTAINS"))
        upsert_edge(db, _edge("ge_ba1", "gn_b", "gn_a", edge_type="RELATED_TO"))
        neighbors = get_neighbors(db, "gn_a", direction="both")
        ids = [n["node_id"] for n in neighbors]
        # gn_b should appear exactly once
        assert ids.count("gn_b") == 1
