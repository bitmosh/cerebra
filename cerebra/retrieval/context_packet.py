"""
ContextPacket builder — assembles the §5 data structure from a retrieval trace.

Two public builders:
  build_context_packet(trace_data, scored_candidates, db_path, *, limit, event_log)
      Assembles a normal (non-abstained) packet from above-floor scored candidates.
      Updates retrieval_traces.context_packet_id in the DB.
      Emits ContextPacketBuilt inspector event.

  build_abstained_packet(trace_data, best_score_seen, *, event_log)
      Builds the abstention form — selected_memory=[], is_abstained=True.
      Does NOT update retrieval_traces.context_packet_id (stays NULL per §5).
      Wired into the search command in Step 10.

Plain-text renderer:
  render_text(packet, limit=10) → str   (§12 format; Step 9 CLI uses this)

See docs/agent/plans/v01_phase4_design.md §5.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from cerebra.inspector.event import InspectorEvent
from cerebra.inspector.sqlite_log import SQLiteEventLog
from cerebra.retrieval.planner import QueryPlan
from cerebra.retrieval.scorer import ScoredCandidate
from cerebra.retrieval.trace import TraceData
from cerebra.storage.db import connect

EXCERPT_MAX_CHARS = 400


# ── Data structures ────────────────────────────────────────────────────────────


@dataclass
class MemoryItem:
    """One entry in ContextPacket.selected_memory."""

    record_id: str
    source_id: str
    chunk_id: str
    content_excerpt: str
    source_path: str
    sku_address: str | None
    score: float
    score_components: dict[str, float]
    retrieval_path: str
    rank: int

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "source_id": self.source_id,
            "chunk_id": self.chunk_id,
            "content_excerpt": self.content_excerpt,
            "source_path": self.source_path,
            "sku_address": self.sku_address,
            "score": self.score,
            "score_components": self.score_components,
            "retrieval_path": self.retrieval_path,
            "rank": self.rank,
        }


@dataclass
class ContextPacket:
    """Assembled retrieval result ready for downstream agent consumption.

    Matches the JSON schema in §5 of v01_phase4_design.md.
    `selected_memory` is always a list (never null) so callers can iterate
    without a null check.
    """

    context_packet_id: str
    packet_version: int
    schema_version: int
    created_at: int
    query: str
    mode: str
    is_abstained: bool
    abstention_rationale: str | None
    retrieval_trace_id: str
    origin_event_ids: list[str]
    selected_memory: list[MemoryItem]
    token_estimate: int
    selected_count: int
    candidate_count: int
    uncertainties: list[str]
    excluded_candidate_count: int
    best_score_seen: float | None = None  # abstained packets only

    def to_dict(self) -> dict:
        d: dict = {
            "context_packet_id": self.context_packet_id,
            "packet_version": self.packet_version,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "query": self.query,
            "mode": self.mode,
            "is_abstained": self.is_abstained,
            "abstention_rationale": self.abstention_rationale,
            "retrieval_trace_id": self.retrieval_trace_id,
            "origin_event_ids": self.origin_event_ids,
            "selected_memory": [item.to_dict() for item in self.selected_memory],
            "token_estimate": self.token_estimate,
            "selected_count": self.selected_count,
            "candidate_count": self.candidate_count,
            "uncertainties": self.uncertainties,
            "excluded_candidate_count": self.excluded_candidate_count,
        }
        if self.best_score_seen is not None:
            d["best_score_seen"] = self.best_score_seen
        return d


# ── Path rendering helper ──────────────────────────────────────────────────────


def _short_path(source_path: str) -> str:
    """Return 'parent/filename'; used as fallback when vault root is unavailable."""
    p = Path(source_path)
    if p.parent.name:
        return f"{p.parent.name}/{p.name}"
    return p.name


def _relative_path(source_path: str, vault_root: Path) -> str:
    """Return a path relative to vault_root; falls back to parent/filename."""
    try:
        return str(Path(source_path).relative_to(vault_root))
    except ValueError:
        return _short_path(source_path)


# ── Builders ───────────────────────────────────────────────────────────────────


def build_context_packet(
    trace_data: TraceData,
    scored_candidates: list[ScoredCandidate],
    db_path: Path,
    *,
    limit: int = 10,
    event_log: SQLiteEventLog | None = None,
) -> ContextPacket:
    """Build a ContextPacket from the above-floor scored candidates.

    `scored_candidates` should be the subset of trace_data.scored_all that
    passed the floor threshold, sorted by rank ascending. The packet caps
    selected_memory at `limit` items.

    Side effects (both happen before returning):
      - UPDATE retrieval_traces.context_packet_id = packet_id
      - Emit ContextPacketBuilt inspector event (if event_log provided)
    """
    plan = trace_data.plan
    trace_id = plan.trace_id

    # Pre-generate the ContextPacketBuilt event_id so it can be included in
    # origin_event_ids before the event is emitted.
    packet_id = f"ctxpkt_{uuid.uuid4().hex[:12]}"
    built_event_id = f"evt_{uuid.uuid4().hex[:12]}"

    # Collect provenance event_ids from the inspector log
    origin_event_ids: list[str] = []
    if event_log is not None:
        for event_type in ("QueryReceived", "QueryPlanned"):
            for row in event_log.query_by_subject(trace_id, event_type):
                origin_event_ids.append(row["event_id"])
    origin_event_ids.append(built_event_id)

    # Cap to limit
    visible = scored_candidates[:limit]
    excluded_count = len(trace_data.scored_all) - len(visible)

    # Fetch source_id and chunk_id from the DB (not stored on ScoredCandidate)
    db_meta: dict[str, dict] = {}
    if visible:
        record_ids = [c.record_id for c in visible]
        placeholders = ",".join("?" * len(record_ids))
        with connect(db_path) as conn:
            rows = conn.execute(
                f"SELECT record_id, source_id, chunk_id "
                f"FROM memory_records WHERE record_id IN ({placeholders})",
                record_ids,
            ).fetchall()
        db_meta = {row["record_id"]: dict(row) for row in rows}

    # vault_root is two levels above data/cerebra.db
    vault_root = db_path.parent.parent

    # Build MemoryItem list; source_path stored as vault-relative so to_dict()
    # and render_text() are consistent — no absolute paths leave this layer.
    items: list[MemoryItem] = []
    for c in visible:
        m = db_meta.get(c.record_id, {})
        items.append(MemoryItem(
            record_id=c.record_id,
            source_id=m.get("source_id") or "",
            chunk_id=m.get("chunk_id") or "",
            content_excerpt=c.content_excerpt[:EXCERPT_MAX_CHARS],
            source_path=_relative_path(c.source_path, vault_root),
            sku_address=c.sku_address,
            score=round(c.score.composite, 6),
            score_components={k: round(v, 6) for k, v in c.score.components.items()},
            retrieval_path=c.retrieval_path,
            rank=c.rank or 0,
        ))

    token_estimate = sum(len(item.content_excerpt) for item in items) // 4

    packet = ContextPacket(
        context_packet_id=packet_id,
        packet_version=1,
        schema_version=1,
        created_at=int(time.time()),
        query=plan.raw_query,
        mode=plan.mode,
        is_abstained=False,
        abstention_rationale=None,
        best_score_seen=None,
        retrieval_trace_id=trace_id,
        origin_event_ids=origin_event_ids,
        selected_memory=items,
        token_estimate=token_estimate,
        selected_count=len(items),
        candidate_count=len(trace_data.scored_all),
        uncertainties=list(plan.staleness_warnings),
        excluded_candidate_count=excluded_count,
    )

    # Persist: set context_packet_id on the trace row
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE retrieval_traces SET context_packet_id = ? WHERE trace_id = ?",
            (packet_id, trace_id),
        )

    # Emit ContextPacketBuilt with the pre-generated event_id
    if event_log is not None:
        event_log.write(InspectorEvent(
            event_type="ContextPacketBuilt",
            actor="retrieval.context_packet",
            summary=f"ContextPacket built: {len(items)} records selected, ~{token_estimate} tokens",
            data={
                "context_packet_id": packet_id,
                "trace_id": trace_id,
                "query": plan.raw_query,
                "selected_count": len(items),
                "candidate_count": len(trace_data.scored_all),
                "token_estimate": token_estimate,
                "is_abstained": False,
            },
            event_id=built_event_id,
            subject_id=packet_id,
        ))

    return packet


def build_abstained_packet(
    trace_data: TraceData,
    best_score_seen: float,
    *,
    event_log: SQLiteEventLog | None = None,
) -> ContextPacket:
    """Build an abstained ContextPacket — no selected memory, is_abstained=True.

    Does NOT update retrieval_traces.context_packet_id (remains NULL per §5;
    abstained traces have no persistent packet reference).

    Wired into the search command in Step 10. Built here so the data
    structure is available for testing and future use.
    """
    plan = trace_data.plan
    trace_id = plan.trace_id
    floor = trace_data.floor

    packet_id = f"ctxpkt_{uuid.uuid4().hex[:12]}"
    built_event_id = f"evt_{uuid.uuid4().hex[:12]}"

    origin_event_ids: list[str] = []
    if event_log is not None:
        for event_type in ("QueryReceived", "QueryPlanned"):
            for row in event_log.query_by_subject(trace_id, event_type):
                origin_event_ids.append(row["event_id"])
    origin_event_ids.append(built_event_id)

    rationale = (
        f"No candidates above salience floor {floor}; "
        f"best score was {best_score_seen:.2f}"
    )

    packet = ContextPacket(
        context_packet_id=packet_id,
        packet_version=1,
        schema_version=1,
        created_at=int(time.time()),
        query=plan.raw_query,
        mode=plan.mode,
        is_abstained=True,
        abstention_rationale=rationale,
        best_score_seen=round(best_score_seen, 6),
        retrieval_trace_id=trace_id,
        origin_event_ids=origin_event_ids,
        selected_memory=[],
        token_estimate=0,
        selected_count=0,
        candidate_count=len(trace_data.scored_all),
        uncertainties=list(plan.staleness_warnings),
        excluded_candidate_count=len(trace_data.scored_all),
    )

    if event_log is not None:
        event_log.write(InspectorEvent(
            event_type="ContextPacketBuilt",
            actor="retrieval.context_packet",
            summary=f"ContextPacket built (abstained): best score {best_score_seen:.2f} < floor {floor}",
            data={
                "context_packet_id": packet_id,
                "trace_id": trace_id,
                "query": plan.raw_query,
                "selected_count": 0,
                "candidate_count": len(trace_data.scored_all),
                "token_estimate": 0,
                "is_abstained": True,
            },
            event_id=built_event_id,
            subject_id=packet_id,
        ))

    return packet


# ── Plain-text renderer ────────────────────────────────────────────────────────


def render_text(packet: ContextPacket, limit: int = 10) -> str:
    """Render a ContextPacket as plain text matching the §12 design.

    Source paths are displayed as 'parent/filename' to avoid leaking
    absolute paths into rendered output.
    """
    lines: list[str] = []

    lines.append(f"\nContextPacket  ID: {packet.context_packet_id}")
    lines.append(f"Query:  {packet.query}")
    lines.append(
        f"Mode:   {packet.mode}  |  "
        f"Trace: {packet.retrieval_trace_id}  |  "
        f"Tokens: ~{packet.token_estimate}"
    )

    if packet.is_abstained:
        lines.append(f"\nAbstained: {packet.abstention_rationale}")
        if packet.uncertainties:
            lines.append("\nUncertainties:")
            for u in packet.uncertainties:
                lines.append(f"  - {u}")
        else:
            lines.append("\nUncertainties: none")
        return "\n".join(lines)

    count = packet.selected_count
    tokens = packet.token_estimate
    lines.append(f"\nSelected memory ({count} records, ~{tokens} tokens):\n")

    for item in packet.selected_memory[:limit]:
        excerpt = item.content_excerpt.replace("\n", " ")
        if len(excerpt) > 80:
            excerpt = excerpt[:79] + "…"
        lines.append(f"[{item.rank}] {item.source_path}  |  Score: {item.score:.2f}  |  {item.retrieval_path}")
        lines.append(f"    {excerpt}")
        lines.append("")

    if packet.uncertainties:
        lines.append("Uncertainties:")
        for u in packet.uncertainties:
            lines.append(f"  - {u}")
    else:
        lines.append("Uncertainties: none")

    return "\n".join(lines)
