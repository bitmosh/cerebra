"""
Lattice-aware sibling deduplication (Phase Lattice Step 2).

After score_candidates() returns a list of ScoredCandidates, dedup_siblings()
collapses lattice sibling groups to a single winner per lineage. Non-lattice
candidates pass through unchanged.

D2 routing rules (applied in priority order):
  1. sku_match       — query has D1; exactly one sibling's sku_address starts with
                       query_d1 → that sibling wins
  2. sku_match_multi — query has D1; multiple siblings match sku_d1 → highest
                       composite wins (tie → earliest created_at)
  3. composite_score — no D1 match (or no query D1) → highest composite wins
                       (tie → earliest created_at)
  Tiebreaker basis   — "earliest_promotion" when created_at broke a composite tie

D6: if no lattice members are found in the candidate list, returns the input
list unchanged and emits nothing (no-op).

Losers within a group have their retrieval_candidates row updated with
  exclusion_reason = "lattice_sibling"
and all rows in the group (winner and losers) receive:
  lattice_sibling_count    = N
  lattice_winner_record_id = winner.record_id
  lattice_routing_basis    = routing_basis string

A second public function, dedup_memory_items(), applies the same lineage-based
logic to MemoryItem lists (used by TruthTower.promote_to_t1() where no query
context is available and no DB updates are needed).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from cerebra.inspector.event import make_event
from cerebra.retrieval.scorer import ScoredCandidate
from cerebra.storage.db import connect

if TYPE_CHECKING:
    from cerebra.inspector.sqlite_log import SQLiteEventLog
    from cerebra.retrieval.context_packet import MemoryItem


def dedup_siblings(
    scored: list[ScoredCandidate],
    query_d1: str | None,
    db_path: Path,
    trace_id: str,
    event_log: SQLiteEventLog | None = None,
) -> list[ScoredCandidate]:
    """Collapse lattice sibling groups to one winner per lineage.

    Returns the deduped list. Non-lattice candidates are returned unchanged.
    Updates retrieval_candidates rows with lattice columns.
    Emits LatticeSiblingResolved once per resolved group.
    """
    if not scored:
        return scored

    record_ids = [c.record_id for c in scored]
    lineage_map: dict[str, str] = {}  # record_id → lattice_lineage_id

    conn = connect(db_path)
    try:
        placeholders = ",".join("?" * len(record_ids))
        rows = conn.execute(
            f"SELECT record_id, lattice_lineage_id FROM memory_records "
            f"WHERE record_id IN ({placeholders}) "
            f"AND is_lattice_member = 1 AND lattice_lineage_id IS NOT NULL",
            record_ids,
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        lineage_map[row["record_id"]] = row["lattice_lineage_id"]

    if not lineage_map:
        return scored  # D6: no-op

    lineage_groups: dict[str, list[ScoredCandidate]] = defaultdict(list)
    non_lattice: list[ScoredCandidate] = []

    for c in scored:
        if c.record_id in lineage_map:
            lineage_groups[lineage_map[c.record_id]].append(c)
        else:
            non_lattice.append(c)

    winners: list[ScoredCandidate] = []
    db_updates: list[tuple[int, str, str, str | None, str]] = []

    for lineage_id, group in lineage_groups.items():
        if len(group) == 1:
            winners.append(group[0])
            continue

        winner, basis = _pick_winner_scored(group, query_d1)
        winners.append(winner)
        n = len(group)

        for c in group:
            candidate_id = f"cand_{trace_id}_{c.record_id}"
            exclusion: str | None = None if c.record_id == winner.record_id else "lattice_sibling"
            db_updates.append((n, winner.record_id, basis, exclusion, candidate_id))

        if event_log is not None:
            event_log.write(
                make_event(
                    event_type="LatticeSiblingResolved",
                    actor="retrieval.lattice_dedup",
                    summary=(
                        f"Sibling group resolved: {n} candidates "
                        f"→ winner={winner.record_id} (basis={basis})"
                    ),
                    data={
                        "lineage_id": lineage_id,
                        "sibling_count": n,
                        "winner_record_id": winner.record_id,
                        "routing_basis": basis,
                        "query_d1": query_d1,
                        "sibling_record_ids": [c.record_id for c in group],
                        "trace_id": trace_id,
                    },
                    subject_id=trace_id,
                )
            )

    if db_updates:
        conn = connect(db_path)
        try:
            for sibling_count, winner_rid, basis, exclusion, candidate_id in db_updates:
                if exclusion is not None:
                    conn.execute(
                        "UPDATE retrieval_candidates "
                        "SET lattice_sibling_count = ?, lattice_winner_record_id = ?, "
                        "    lattice_routing_basis = ?, exclusion_reason = ? "
                        "WHERE candidate_id = ?",
                        (sibling_count, winner_rid, basis, exclusion, candidate_id),
                    )
                else:
                    conn.execute(
                        "UPDATE retrieval_candidates "
                        "SET lattice_sibling_count = ?, lattice_winner_record_id = ?, "
                        "    lattice_routing_basis = ? "
                        "WHERE candidate_id = ?",
                        (sibling_count, winner_rid, basis, candidate_id),
                    )
            conn.commit()
        finally:
            conn.close()

    return winners + non_lattice


def dedup_memory_items(
    items: list[MemoryItem],
    db_path: Path,
) -> list[MemoryItem]:
    """Dedup lattice siblings in a MemoryItem list.

    Used by TruthTower.promote_to_t1() where no query context is available.
    No retrieval_candidates DB updates and no event emission — T1 promotion
    handles its own events.

    Records not in any lineage group are returned unchanged.
    """
    if len(items) <= 1:
        return items

    record_ids = [mi.record_id for mi in items]
    lineage_map: dict[str, str] = {}
    created_at_map: dict[str, int] = {}

    conn = connect(db_path)
    try:
        placeholders = ",".join("?" * len(record_ids))
        rows = conn.execute(
            f"SELECT record_id, lattice_lineage_id, created_at FROM memory_records "
            f"WHERE record_id IN ({placeholders}) "
            f"AND is_lattice_member = 1 AND lattice_lineage_id IS NOT NULL",
            record_ids,
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        lineage_map[row["record_id"]] = row["lattice_lineage_id"]
        created_at_map[row["record_id"]] = row["created_at"]

    if not lineage_map:
        return items  # D6: no-op

    lineage_groups: dict[str, list[MemoryItem]] = defaultdict(list)
    non_lattice: list[MemoryItem] = []

    for mi in items:
        if mi.record_id in lineage_map:
            lineage_groups[lineage_map[mi.record_id]].append(mi)
        else:
            non_lattice.append(mi)

    winners_mi: list[MemoryItem] = []
    for group in lineage_groups.values():
        if len(group) == 1:
            winners_mi.append(group[0])
            continue
        max_score = max(mi.score for mi in group)
        top = [mi for mi in group if mi.score == max_score]
        if len(top) == 1:
            winners_mi.append(top[0])
        else:
            winner = min(top, key=lambda mi: created_at_map.get(mi.record_id, 0))
            winners_mi.append(winner)

    return winners_mi + non_lattice


# ── Internal helpers ──────────────────────────────────────────────────────────


def _pick_winner_scored(
    group: list[ScoredCandidate],
    query_d1: str | None,
) -> tuple[ScoredCandidate, str]:
    """Apply D2 routing rules; return (winner, routing_basis)."""
    if query_d1 is not None:
        d1_matches = [
            c for c in group if c.sku_address and c.sku_address.split("::")[0] == query_d1
        ]
        if len(d1_matches) == 1:
            return d1_matches[0], "sku_match"
        if len(d1_matches) > 1:
            return _best_composite(d1_matches, "sku_match_multi")
        return _best_composite(group, "composite_score")
    return _best_composite(group, "composite_score")


def _best_composite(
    candidates: list[ScoredCandidate],
    basis: str,
) -> tuple[ScoredCandidate, str]:
    """Highest composite score; tiebreak by earliest created_at."""
    max_score = max(c.score.composite for c in candidates)
    top = [c for c in candidates if c.score.composite == max_score]
    if len(top) == 1:
        return top[0], basis
    winner = min(top, key=lambda c: c.created_at)
    return winner, "earliest_promotion"
