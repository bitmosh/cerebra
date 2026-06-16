"""
Graph exporter — builds and writes cerebra/v1 JSON for LumaWeave.

Output: {vault_root}/.cerebra/graph.json
Schema: cerebra/v1

Only active sources and active memory_records with completed sku_assignments
are exported. Stale, archived, and tombstoned records are omitted entirely.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cerebra.inspector.event import make_event
from cerebra.inspector.sqlite_log import SQLiteEventLog
from cerebra.storage.db import connect

from cerebra.graph.model import ExportStats

# ── Lookup tables ─────────────────────────────────────────────────────────────

# D1 quadrant index (d1 // 4) → cluster color name
_D1_QUADRANT_CLUSTER = ["azure", "gold", "purple", "teal"]

# D1 quadrant index → quadrant name
_D1_QUADRANT_NAME = ["Empirical", "Generative", "Normative", "Relational"]

# detected_type → cluster color for spine nodes
_DETECTED_TYPE_CLUSTER: dict[str, str] = {
    "markdown": "slate",
    "code": "gray",
    "graph": "teal",
}
_DEFAULT_SOURCE_CLUSTER = "azure"

# Max sku-proximity edges per record node (matches LumaWeave tag-overlap cap)
_SKU_PROXIMITY_CAP = 5

# Max total nodes exported (alphabetical source order, then chunk_index within source)
_MAX_NODES = 2000


# ── Helpers ───────────────────────────────────────────────────────────────────


def _ts_to_iso(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _source_cluster(detected_type: str) -> str:
    return _DETECTED_TYPE_CLUSTER.get(detected_type.lower(), _DEFAULT_SOURCE_CLUSTER)


def _record_cluster(d1: int) -> str:
    q = d1 // 4
    return _D1_QUADRANT_CLUSTER[q] if 0 <= q < 4 else "azure"


def _record_quadrant_name(d1: int) -> str:
    q = d1 // 4
    return _D1_QUADRANT_NAME[q] if 0 <= q < 4 else "Unknown"


def _source_size(total_tokens: int) -> float:
    return min(24.0, max(10.0, total_tokens / 500))


def _record_size(token_estimate: int) -> float:
    return min(12.0, max(4.0, token_estimate / 100))


def _record_label(
    heading_path: str | None, doc_title: str | None, record_id: str
) -> str:
    if heading_path:
        return heading_path
    if doc_title:
        return doc_title
    return f"record_{record_id[:8]}"


def _d1_category_name(d1: int) -> str:
    try:
        from cerebra.cognition.sku_categories import D1Category
        return D1Category(d1).name
    except (ValueError, ImportError):
        return f"D1_{d1}"


def _d9_name(d9: int) -> str:
    try:
        from cerebra.cognition.sku import D9Modality
        return D9Modality(d9).name
    except (ValueError, ImportError):
        return f"D9_{d9}"


def _d10_name(d10: int) -> str:
    try:
        from cerebra.cognition.sku import D10Provenance
        return D10Provenance(d10).name
    except (ValueError, ImportError):
        return f"D10_{d10}"


# ── Core build function ───────────────────────────────────────────────────────


def build_graph(db_path: Path, vault_path: Path) -> dict[str, Any]:
    """Query the vault and return the complete cerebra/v1 graph dict."""
    import importlib.metadata

    try:
        cerebra_version = importlib.metadata.version("cerebra")
    except Exception:
        cerebra_version = "unknown"

    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with connect(db_path) as conn:
        # ── Sources ───────────────────────────────────────────────────────────
        source_rows = conn.execute(
            """
            SELECT
                s.source_id,
                s.canonical_path,
                s.detected_type,
                s.lifecycle_state,
                s.ingested_at,
                COALESCE((
                    SELECT SUM(c.token_estimate)
                    FROM memory_records mr
                    JOIN chunks c ON mr.chunk_id = c.chunk_id
                    WHERE mr.source_id = s.source_id AND mr.lifecycle_state = 'active'
                ), 0) AS total_tokens,
                COALESCE((
                    SELECT COUNT(*)
                    FROM memory_records mr
                    WHERE mr.source_id = s.source_id AND mr.lifecycle_state = 'active'
                ), 0) AS record_count
            FROM sources s
            WHERE s.lifecycle_state = 'active'
              AND s.canonical_path NOT LIKE 'cerebra://%'
            ORDER BY s.canonical_path
            """,
        ).fetchall()

        # ── Records with sku_assignments ──────────────────────────────────────
        record_rows = conn.execute(
            """
            SELECT
                mr.record_id,
                mr.source_id,
                mr.lifecycle_state,
                sa.sku_address,
                sa.d1,
                sa.d1_confidence,
                sa.d9,
                sa.d10,
                c.heading_path,
                c.chunk_index,
                c.token_estimate,
                c.document_id,
                d.title AS doc_title,
                s.canonical_path,
                s.ingested_at,
                s.detected_type
            FROM memory_records mr
            JOIN sku_assignments sa ON mr.record_id = sa.record_id
            JOIN chunks c ON mr.chunk_id = c.chunk_id
            JOIN documents d ON c.document_id = d.document_id
            JOIN sources s ON mr.source_id = s.source_id
            WHERE mr.lifecycle_state = 'active'
            ORDER BY s.canonical_path, c.chunk_index
            """,
        ).fetchall()

        # Unclassified active records (present in memory_records but no sku_assignment)
        unclassified_count: int = conn.execute(
            """
            SELECT COUNT(*) FROM memory_records mr
            WHERE mr.lifecycle_state = 'active'
              AND NOT EXISTS (
                  SELECT 1 FROM sku_assignments sa WHERE sa.record_id = mr.record_id
              )
            """,
        ).fetchone()[0]

    # ── Build node lists ──────────────────────────────────────────────────────

    nodes: list[dict[str, Any]] = []
    total_node_cap = _MAX_NODES

    # Track which source_ids ended up in nodes (after cap)
    exported_source_ids: set[str] = set()

    # Spine nodes
    for row in source_rows:
        if len(nodes) >= total_node_cap:
            break
        src_id = row["source_id"]
        basename = Path(row["canonical_path"]).name
        cluster = _source_cluster(row["detected_type"])
        size = _source_size(int(row["total_tokens"]))
        nodes.append({
            "id": f"source:{src_id}",
            "label": basename,
            "fullLabel": row["canonical_path"],
            "type": "spine",
            "cluster": cluster,
            "status": row["lifecycle_state"],
            "tags": ["source", row["detected_type"]],
            "size": round(size, 2),
            "path": row["canonical_path"],
            "lastModified": _ts_to_iso(row["ingested_at"]),
            "raw": {
                "detected_type": row["detected_type"],
                "source_id": src_id,
                "record_count": int(row["record_count"]),
                "total_tokens": int(row["total_tokens"]),
                "sourceAdapter": "cerebra-vault",
            },
        })
        exported_source_ids.add(src_id)

    spine_count = len(nodes)

    # Record nodes (only for exported sources, within cap)
    exported_record_ids: set[str] = set()

    for row in record_rows:
        if len(nodes) >= total_node_cap:
            break
        if row["source_id"] not in exported_source_ids:
            continue

        rec_id = row["record_id"]
        d1 = int(row["d1"])
        d1_confidence = float(row["d1_confidence"])
        cluster = _record_cluster(d1)
        size = _record_size(int(row["token_estimate"]))
        basename = Path(row["canonical_path"]).name
        heading = row["heading_path"] or ""
        label = _record_label(heading or None, row["doc_title"], rec_id)
        full_label = f"{basename} › {heading}" if heading else basename
        dim_factor = 0.7 if d1_confidence < 0.5 else 1.0

        nodes.append({
            "id": f"record:{rec_id}",
            "label": label,
            "fullLabel": full_label,
            "type": "memory_record",
            "cluster": cluster,
            "status": row["lifecycle_state"],
            "tags": [_d1_category_name(d1), _d9_name(int(row["d9"])), f"q{d1 // 4}"],
            "size": round(size, 2),
            "path": row["canonical_path"],
            "lastModified": _ts_to_iso(row["ingested_at"]),
            "raw": {
                "sku_address": row["sku_address"],
                "d1": d1,
                "d1_category": _d1_category_name(d1),
                "d1_confidence": round(d1_confidence, 6),
                "d9_modality": _d9_name(int(row["d9"])),
                "d10_provenance": _d10_name(int(row["d10"])),
                "quadrant": d1 // 4,
                "quadrant_name": _record_quadrant_name(d1),
                "detected_type": row["detected_type"],
                "token_estimate": int(row["token_estimate"]),
                "chunk_index": int(row["chunk_index"]),
                "heading_path": heading,
                "record_id": rec_id,
                "source_id": row["source_id"],
                "dimFactor": dim_factor,
                "sourceAdapter": "cerebra-vault",
            },
        })
        exported_record_ids.add(rec_id)

    record_count = len(nodes) - spine_count

    # ── Build edges ───────────────────────────────────────────────────────────

    edges: list[dict[str, Any]] = []
    edges_by_type: dict[str, int] = {
        "contains": 0,
        "describes": 0,
        "sku-proximity": 0,
        "sku-exact": 0,
    }

    # Index record rows by record_id for edge building (only exported records)
    record_index: dict[str, dict] = {}
    for row in record_rows:
        if row["record_id"] in exported_record_ids:
            record_index[row["record_id"]] = dict(row)

    # contains: source → each of its records
    for rec_id, rec in record_index.items():
        src_id = rec["source_id"]
        if src_id not in exported_source_ids:
            continue
        edges.append({
            "id": f"edge-{src_id}-{rec_id}-contains",
            "source": f"source:{src_id}",
            "target": f"record:{rec_id}",
            "type": "contains",
            "weight": 0.4,
            "bidirectional": False,
            "provenance": {"source": "cerebra-db", "detail": "source_id FK"},
            "raw": {"label": None, "color": "rgba(107,114,128,0.35)"},
        })
        edges_by_type["contains"] += 1

    # describes: adjacent records within the same document, by chunk_index
    by_document: dict[str, list[dict]] = {}
    for rec_id, rec in record_index.items():
        doc_id = rec["document_id"]
        by_document.setdefault(doc_id, []).append(rec)

    for doc_id, doc_records in by_document.items():
        sorted_recs = sorted(doc_records, key=lambda r: int(r["chunk_index"]))
        for i in range(len(sorted_recs) - 1):
            a = sorted_recs[i]
            b = sorted_recs[i + 1]
            a_id = a["record_id"]
            b_id = b["record_id"]
            edges.append({
                "id": f"edge-{a_id}-{b_id}-describes",
                "source": f"record:{a_id}",
                "target": f"record:{b_id}",
                "type": "describes",
                "weight": 0.65,
                "bidirectional": False,
                "provenance": {"source": "cerebra-db", "detail": "chunk adjacency"},
                "raw": {"label": None, "color": "rgba(79,163,224,0.40)"},
            })
            edges_by_type["describes"] += 1

    # sku-proximity: records sharing the same d1, cap 5 per node
    by_d1: dict[int, list[str]] = {}
    for rec_id, rec in record_index.items():
        d1 = int(rec["d1"])
        by_d1.setdefault(d1, []).append(rec_id)

    prox_count: dict[str, int] = {}

    for d1, group_ids in by_d1.items():
        if len(group_ids) < 2:
            continue
        group_ids_sorted = sorted(group_ids)
        d1_count = len(group_ids_sorted)
        weight = round(min(0.5, d1_count / 20), 4)

        for i, a_id in enumerate(group_ids_sorted):
            for b_id in group_ids_sorted[i + 1:]:
                if prox_count.get(a_id, 0) >= _SKU_PROXIMITY_CAP:
                    break
                if prox_count.get(b_id, 0) >= _SKU_PROXIMITY_CAP:
                    continue
                edges.append({
                    "id": f"edge-{a_id}-{b_id}-sku-proximity",
                    "source": f"record:{a_id}",
                    "target": f"record:{b_id}",
                    "type": "sku-proximity",
                    "weight": weight,
                    "bidirectional": True,
                    "provenance": {"source": "cerebra-db", "detail": "shared d1"},
                    "raw": {"label": None, "color": "rgba(100,217,164,0.30)"},
                })
                edges_by_type["sku-proximity"] += 1
                prox_count[a_id] = prox_count.get(a_id, 0) + 1
                prox_count[b_id] = prox_count.get(b_id, 0) + 1

    # sku-exact: records with identical sku_address (no cap)
    by_sku: dict[str, list[str]] = {}
    for rec_id, rec in record_index.items():
        sku = rec["sku_address"]
        by_sku.setdefault(sku, []).append(rec_id)

    for sku, group_ids in by_sku.items():
        if len(group_ids) < 2:
            continue
        group_ids_sorted = sorted(group_ids)
        for i, a_id in enumerate(group_ids_sorted):
            for b_id in group_ids_sorted[i + 1:]:
                edges.append({
                    "id": f"edge-{a_id}-{b_id}-sku-exact",
                    "source": f"record:{a_id}",
                    "target": f"record:{b_id}",
                    "type": "sku-exact",
                    "weight": 0.9,
                    "bidirectional": True,
                    "provenance": {"source": "cerebra-db", "detail": "identical sku_address"},
                    "raw": {"label": None, "color": "rgba(224,168,79,0.55)"},
                })
                edges_by_type["sku-exact"] += 1

    # ── Assemble graph dict ───────────────────────────────────────────────────

    total_edges = sum(edges_by_type.values())

    graph: dict[str, Any] = {
        "schemaVersion": "cerebra/v1",
        "metadata": {
            "schemaVersion": "cerebra/v1",
            "generatedAt": generated_at,
            "generator": f"cerebra-graph-exporter@{cerebra_version}",
            "vaultPath": str(vault_path),
            "cerebraVersion": cerebra_version,
            "stats": {
                "nodeCount": len(nodes),
                "edgeCount": total_edges,
                "nodesByType": {
                    "spine": spine_count,
                    "memory_record": record_count,
                },
                "edgesByType": edges_by_type,
                "activeSourceCount": spine_count,
                "activeRecordCount": record_count,
                "classifiedRecordCount": record_count,
                "unclassifiedRecordCount": unclassified_count,
            },
        },
        "nodes": nodes,
        "edges": edges,
    }

    return graph


# ── Public entry point ────────────────────────────────────────────────────────


def export_graph(
    vault_path: Path,
    *,
    out_path: Path | None = None,
    event_log: SQLiteEventLog | None = None,
) -> ExportStats:
    """Export the vault graph to a cerebra/v1 JSON file.

    Writes to {vault_path}/.cerebra/graph.json by default, or to out_path if
    provided. Returns ExportStats. Emits GraphExported to event_log if supplied.
    """
    t0 = time.monotonic()

    db_path = vault_path / "data" / "cerebra.db"
    if out_path is None:
        cerebra_dir = vault_path / ".cerebra"
        cerebra_dir.mkdir(exist_ok=True)
        out_path = cerebra_dir / "graph.json"
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)

    graph = build_graph(db_path, vault_path)

    out_path.write_text(json.dumps(graph, indent=2))

    meta = graph["metadata"]["stats"]
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    stats = ExportStats(
        node_count=meta["nodeCount"],
        edge_count=meta["edgeCount"],
        spine_count=meta["nodesByType"]["spine"],
        record_count=meta["nodesByType"]["memory_record"],
        classified_count=meta["classifiedRecordCount"],
        unclassified_count=meta["unclassifiedRecordCount"],
        edges_by_type=dict(meta["edgesByType"]),
        out_path=out_path,
        elapsed_ms=elapsed_ms,
    )

    if event_log is not None:
        event_log.write(make_event(
            event_type="GraphExported",
            actor="graph_exporter",
            summary=(
                f"Exported {stats.node_count} nodes, {stats.edge_count} edges "
                f"to {out_path}"
            ),
            data=stats.as_dict(),
        ))

    return stats
