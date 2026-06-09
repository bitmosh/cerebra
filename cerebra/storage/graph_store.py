"""
Graph store — CRUD and traversal for graph_nodes and graph_edges.

Node and edge identity
──────────────────────
node_id and edge_id are caller-supplied. For entity-backed nodes (those with
a non-null entity_id) use make_node_id() to derive a stable, deterministic ID
from the entity. For non-entity nodes (Entity, Topic, Decision, …) use
make_node_id() with a synthetic key or pass a uuid-based string directly.

Upsert semantics
────────────────
upsert_node and upsert_edge use INSERT … ON CONFLICT DO UPDATE. Immutable
fields (node_type, entity_id, entity_table, origin_event_id, created_at) are
never overwritten after the first write. Mutable fields (label, sku_address,
lifecycle_state, payload_json, updated_at for nodes; confidence, weight,
evidence, lifecycle_state, payload_json, updated_at for edges) are updated on
conflict.

updated_at discipline
─────────────────────
No SQLite trigger manages updated_at. The caller must pass the current epoch
seconds. This is deliberate — triggers fire silently without inspector events.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path
from typing import Any

from cerebra.storage.db import connect

# Valid lifecycle states for nodes and edges.
LIFECYCLE_STATES = frozenset({"active", "archived", "tombstoned", "stale"})

# Edge types that define upward traversal in walk_parent_chain.
# A node's "parent" is reachable by following these edge types from it.
_PARENT_OUTBOUND_TYPES = frozenset({"DERIVED_FROM", "PART_OF"})  # outbound: node → parent
_PARENT_INBOUND_TYPES = frozenset({"CONTAINS"})                  # inbound: parent → node


# ── ID generation ─────────────────────────────────────────────────────────────


def make_node_id(key: str) -> str:
    """Derive a stable node_id from an arbitrary string key.

    For entity-backed nodes, key should be f"{entity_table}:{entity_id}".
    For synthetic nodes, key should be unique within the vault.
    """
    digest = hashlib.sha256(key.encode()).hexdigest()[:12]
    return f"gn_{digest}"


def make_edge_id() -> str:
    """Generate a random edge_id."""
    return f"ge_{uuid.uuid4().hex[:12]}"


# ── Nodes ──────────────────────────────────────────────────────────────────────


def upsert_node(db_path: Path, node: dict[str, Any]) -> str:
    """Insert or update a graph node. Returns the node_id.

    Required keys: node_id, node_type, label, lifecycle_state, payload_json,
                   created_at, updated_at.
    Optional keys: entity_id, entity_table, sku_address, origin_event_id.

    Immutable on conflict: node_type, entity_id, entity_table,
                           origin_event_id, created_at, schema_version.
    Mutable on conflict:   label, sku_address, lifecycle_state,
                           payload_json, updated_at.
    """
    node.setdefault("entity_id", None)
    node.setdefault("entity_table", None)
    node.setdefault("sku_address", None)
    node.setdefault("origin_event_id", None)
    node.setdefault("schema_version", 1)

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO graph_nodes (
                node_id, node_type, label, entity_id, entity_table,
                sku_address, lifecycle_state, origin_event_id,
                payload_json, created_at, updated_at, schema_version
            ) VALUES (
                :node_id, :node_type, :label, :entity_id, :entity_table,
                :sku_address, :lifecycle_state, :origin_event_id,
                :payload_json, :created_at, :updated_at, :schema_version
            )
            ON CONFLICT(node_id) DO UPDATE SET
                label           = excluded.label,
                sku_address     = excluded.sku_address,
                lifecycle_state = excluded.lifecycle_state,
                payload_json    = excluded.payload_json,
                updated_at      = excluded.updated_at
            """,
            node,
        )
    return str(node["node_id"])


def get_node(db_path: Path, node_id: str) -> dict[str, Any] | None:
    """Return the node row for node_id, or None."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM graph_nodes WHERE node_id = ?", (node_id,)
        ).fetchone()
    return dict(row) if row else None


def get_node_for_entity(
    db_path: Path, entity_id: str, entity_table: str
) -> dict[str, Any] | None:
    """Return the node for a given entity, or None if not yet in the graph."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM graph_nodes WHERE entity_id = ? AND entity_table = ?",
            (entity_id, entity_table),
        ).fetchone()
    return dict(row) if row else None


def set_node_lifecycle(
    db_path: Path, node_id: str, lifecycle_state: str
) -> None:
    """Transition a node's lifecycle_state. Also stamps updated_at."""
    now = int(time.time())
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE graph_nodes SET lifecycle_state = ?, updated_at = ? WHERE node_id = ?",
            (lifecycle_state, now, node_id),
        )


# ── Edges ──────────────────────────────────────────────────────────────────────


def upsert_edge(db_path: Path, edge: dict[str, Any]) -> str:
    """Insert or update a graph edge. Returns the edge_id.

    Required keys: edge_id, edge_type, source_node_id, target_node_id,
                   confidence, weight, created_by, lifecycle_state,
                   payload_json, created_at, updated_at.
    Optional keys: evidence, origin_event_id.

    Immutable on conflict: edge_type, source_node_id, target_node_id,
                           origin_event_id, created_at, schema_version.
    Mutable on conflict:   confidence, weight, evidence, lifecycle_state,
                           payload_json, updated_at.
    """
    edge.setdefault("evidence", None)
    edge.setdefault("origin_event_id", None)
    edge.setdefault("schema_version", 1)

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO graph_edges (
                edge_id, edge_type, source_node_id, target_node_id,
                confidence, weight, evidence, created_by,
                origin_event_id, lifecycle_state, payload_json,
                created_at, updated_at, schema_version
            ) VALUES (
                :edge_id, :edge_type, :source_node_id, :target_node_id,
                :confidence, :weight, :evidence, :created_by,
                :origin_event_id, :lifecycle_state, :payload_json,
                :created_at, :updated_at, :schema_version
            )
            ON CONFLICT(edge_id) DO UPDATE SET
                confidence      = excluded.confidence,
                weight          = excluded.weight,
                evidence        = excluded.evidence,
                lifecycle_state = excluded.lifecycle_state,
                payload_json    = excluded.payload_json,
                updated_at      = excluded.updated_at
            """,
            edge,
        )
    return str(edge["edge_id"])


def get_edge(db_path: Path, edge_id: str) -> dict[str, Any] | None:
    """Return the edge row for edge_id, or None."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM graph_edges WHERE edge_id = ?", (edge_id,)
        ).fetchone()
    return dict(row) if row else None


def set_edge_lifecycle(
    db_path: Path, edge_id: str, lifecycle_state: str
) -> None:
    """Transition an edge's lifecycle_state. Also stamps updated_at."""
    now = int(time.time())
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE graph_edges SET lifecycle_state = ?, updated_at = ? WHERE edge_id = ?",
            (lifecycle_state, now, edge_id),
        )


# ── Traversal ─────────────────────────────────────────────────────────────────


def get_neighbors(
    db_path: Path,
    node_id: str,
    *,
    direction: str = "outbound",
    edge_type: str | None = None,
    lifecycle_state: str = "active",
) -> list[dict[str, Any]]:
    """Return neighboring nodes reachable from node_id.

    direction: 'outbound' | 'inbound' | 'both'
    edge_type: filter to a single edge type (None = all types)
    lifecycle_state: filter edges and returned nodes by lifecycle state
    """
    params: list[Any]

    if direction == "outbound":
        join_col, other_col = "source_node_id", "target_node_id"
    elif direction == "inbound":
        join_col, other_col = "target_node_id", "source_node_id"
    elif direction == "both":
        # Recurse: union of both directions
        outbound = get_neighbors(
            db_path, node_id,
            direction="outbound", edge_type=edge_type, lifecycle_state=lifecycle_state
        )
        inbound = get_neighbors(
            db_path, node_id,
            direction="inbound", edge_type=edge_type, lifecycle_state=lifecycle_state
        )
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for n in outbound + inbound:
            if n["node_id"] not in seen:
                seen.add(n["node_id"])
                result.append(n)
        return result
    else:
        raise ValueError(f"direction must be 'outbound', 'inbound', or 'both'; got {direction!r}")

    edge_filter = "AND e.edge_type = ?" if edge_type else ""
    params = [node_id, lifecycle_state, lifecycle_state]
    if edge_type:
        params.insert(2, edge_type)

    sql = f"""
        SELECT n.*
          FROM graph_nodes n
          JOIN graph_edges e ON n.node_id = e.{other_col}
         WHERE e.{join_col} = ?
           AND e.lifecycle_state = ?
           {edge_filter}
           AND n.lifecycle_state = ?
    """
    with connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_1hop(
    db_path: Path,
    node_id: str,
    *,
    lifecycle_state: str = "active",
) -> dict[str, list[dict[str, Any]]]:
    """Return all 1-hop neighbors in both directions.

    Returns {"outbound": [...nodes...], "inbound": [...nodes...]}.
    """
    return {
        "outbound": get_neighbors(
            db_path, node_id, direction="outbound", lifecycle_state=lifecycle_state
        ),
        "inbound": get_neighbors(
            db_path, node_id, direction="inbound", lifecycle_state=lifecycle_state
        ),
    }


def get_sibling_targets(
    db_path: Path,
    node_id: str,
    *,
    lifecycle_state: str = "active",
) -> list[str]:
    """Return node_ids of all nodes reachable from node_id via any outbound edge.

    Used for sibling pointer traversal in SKU retrieval (step 4).
    Returns node_ids only (not full dicts) for efficiency.
    """
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT target_node_id
              FROM graph_edges
             WHERE source_node_id = ?
               AND lifecycle_state = ?
            """,
            (node_id, lifecycle_state),
        ).fetchall()
    return [r[0] for r in rows]


def walk_parent_chain(
    db_path: Path,
    node_id: str,
    *,
    lifecycle_state: str = "active",
    max_depth: int = 10,
) -> list[dict[str, Any]]:
    """Walk the provenance chain from node_id toward its root(s).

    Follows outbound DERIVED_FROM and PART_OF edges, plus inbound CONTAINS
    edges (i.e. "who contains this node?"). Returns nodes in order from the
    starting node's immediate parents toward the root, without including
    node_id itself.

    max_depth guards against cycles (should not exist, but defensive).
    """
    visited: set[str] = {node_id}
    chain: list[dict[str, Any]] = []
    current_ids = [node_id]

    for _ in range(max_depth):
        if not current_ids:
            break
        next_ids: list[str] = []
        for cid in current_ids:
            # Outbound: DERIVED_FROM, PART_OF → target is the parent
            outbound_parents = get_neighbors(
                db_path, cid,
                direction="outbound", lifecycle_state=lifecycle_state
            )
            outbound_parents = [
                n for n in outbound_parents
                if n["node_id"] not in visited
                and _edge_type_between(db_path, cid, n["node_id"]) in _PARENT_OUTBOUND_TYPES
            ]
            # Inbound: CONTAINS → source is the parent
            inbound_parents = get_neighbors(
                db_path, cid,
                direction="inbound", lifecycle_state=lifecycle_state
            )
            inbound_parents = [
                n for n in inbound_parents
                if n["node_id"] not in visited
                and _edge_type_between(db_path, n["node_id"], cid) in _PARENT_INBOUND_TYPES
            ]
            for parent in outbound_parents + inbound_parents:
                if parent["node_id"] not in visited:
                    visited.add(parent["node_id"])
                    chain.append(parent)
                    next_ids.append(parent["node_id"])
        current_ids = next_ids

    return chain


def _edge_type_between(db_path: Path, source_id: str, target_id: str) -> str | None:
    """Return the edge_type of the first active edge from source to target, or None."""
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT edge_type FROM graph_edges
             WHERE source_node_id = ? AND target_node_id = ?
               AND lifecycle_state = 'active'
             LIMIT 1
            """,
            (source_id, target_id),
        ).fetchone()
    return row[0] if row else None
