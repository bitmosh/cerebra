"""
Salience scorer — computes per-component scores and assembles ScoredCandidate objects.

Five components (§4 of design doc):
  semantic   0.40  — cosine similarity from vector search (already in [0,1])
  lexical    0.25  — FTS5 BM25 normalized within the candidate set (abs(rank)/max_abs)
  sku_match  0.15  — binary D1 match (1.0 or 0.0)
  recency    0.10  — exponential decay with 365-day half-life
  lifecycle  0.10  — constant 1.0 in Phase 4 (tombstoned records pre-filtered by traversal)

Caller flow:
  raw = run_traversal(plan, db_path)
  scored = score_candidates(raw, plan, db_path)

See docs/agent/plans/v01_phase4_design.md §4.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path

from cerebra._primitives.score_composer import CompositeScore, compose
from cerebra.inspector.event import make_event
from cerebra.inspector.sqlite_log import SQLiteEventLog
from cerebra.retrieval.planner import QueryPlan
from cerebra.retrieval.traversal import RawCandidate
from cerebra.storage.db import connect

_WEIGHTS = {
    "semantic": 0.40,
    "lexical": 0.25,
    "sku_match": 0.15,
    "recency": 0.10,
    "lifecycle": 0.10,
}

_CONTENT_EXCERPT_LEN = 300


@dataclass
class ScoredCandidate:
    """A candidate with its full salience score and metadata, ready for ContextPacket."""

    record_id: str
    step_surfaced: str    # first traversal step that surfaced this record
    retrieval_path: str
    score: CompositeScore
    source_path: str
    content_excerpt: str
    sku_address: str | None
    created_at: int
    rank: int | None = None


# ── Normalization ──────────────────────────────────────────────────────────────


def _normalize_lexical(rank: float, ranks: list[float]) -> float:
    """Normalize a BM25 rank to [0, 1] relative to the candidate set.

    FTS5 returns negative ranks; more negative = better match.
    Formula: abs(rank) / max_abs — best match → 1.0, worst → near 0.0.
    """
    max_abs = max(abs(r) for r in ranks) if ranks else 1.0
    if max_abs == 0.0:
        return 0.0
    return abs(rank) / max_abs


def _normalize_recency(created_at: int, now: int) -> float:
    """Exponential decay with 365-day half-life."""
    age_days = (now - created_at) / 86400
    return math.exp(-age_days / 365)


# ── Main scorer ────────────────────────────────────────────────────────────────


def score_candidates(
    candidates: list[RawCandidate],
    plan: QueryPlan,
    db_path: Path,
    *,
    now: int | None = None,
    event_log: SQLiteEventLog | None = None,
) -> list[ScoredCandidate]:
    """Score a list of RawCandidates and return sorted ScoredCandidates.

    Fetches record metadata from the database. Normalizes lexical scores
    relative to the full candidate set. Returns candidates sorted by
    composite score descending, with rank assigned 1-based.

    Emits SalienceScored inspector event when event_log is provided.
    """
    if not candidates:
        return []

    _now = now if now is not None else int(time.time())

    # ── Fetch metadata for all candidates in one query ────────────────────────
    record_ids = [c.record_id for c in candidates]
    placeholders = ", ".join("?" * len(record_ids))
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                m.record_id,
                m.content,
                m.created_at,
                m.lifecycle_state,
                m.sku_address,
                s.canonical_path AS source_path
            FROM memory_records m
            LEFT JOIN sources s ON m.source_id = s.source_id
            WHERE m.record_id IN ({placeholders})
            """,
            record_ids,
        ).fetchall()

    meta: dict[str, dict] = {
        row["record_id"]: dict(row) for row in rows
    }

    # ── Lexical normalization: collect all raw ranks in the candidate set ─────
    lex_ranks = [
        c.lexical_score
        for c in candidates
        if c.lexical_score is not None
    ]

    # ── Score each candidate ──────────────────────────────────────────────────
    scored: list[ScoredCandidate] = []
    for raw in candidates:
        m = meta.get(raw.record_id)
        if m is None:
            continue  # record disappeared between traversal and scoring (edge case)

        # semantic: already in [0,1] from cosine_search (L2-normalized)
        semantic = raw.semantic_score if raw.semantic_score is not None else 0.0

        # lexical: normalize relative to the full candidate set
        if raw.lexical_score is not None and lex_ranks:
            lexical = _normalize_lexical(raw.lexical_score, lex_ranks)
        else:
            lexical = 0.0

        # sku_match: binary D1 match (1.0 or 0.0)
        sku_match = 1.0 if raw.sku_d1_match else 0.0

        # recency: exponential decay, 365-day half-life
        recency = _normalize_recency(m["created_at"], _now)

        # lifecycle: constant 1.0 in Phase 4 (tombstoned records pre-filtered by traversal)
        lifecycle = 1.0

        score = compose(
            components={
                "semantic": semantic,
                "lexical": lexical,
                "sku_match": sku_match,
                "recency": recency,
                "lifecycle": lifecycle,
            },
            weights=_WEIGHTS,
        )

        content = m["content"] or ""
        scored.append(ScoredCandidate(
            record_id=raw.record_id,
            step_surfaced=raw.step_surfaced,
            retrieval_path=raw.retrieval_path,
            score=score,
            source_path=m["source_path"] or "",
            content_excerpt=content[:_CONTENT_EXCERPT_LEN],
            sku_address=m["sku_address"],
            created_at=m["created_at"],
        ))

    # ── Sort and rank ─────────────────────────────────────────────────────────
    scored.sort(key=lambda c: c.score.composite, reverse=True)
    for i, c in enumerate(scored):
        c.rank = i + 1

    # ── Inspector event ───────────────────────────────────────────────────────
    if event_log is not None and scored:
        top = scored[0].score.composite
        mean = sum(c.score.composite for c in scored) / len(scored)
        floor = 0.35
        above = sum(1 for c in scored if c.score.composite >= floor)
        event_log.write(make_event(
            event_type="SalienceScored",
            actor="retrieval.scorer",
            summary=(
                f"Scored {len(scored)} candidates; "
                f"top={top:.2f}, mean={mean:.2f}, floor={floor}"
            ),
            data={
                "trace_id": plan.trace_id,
                "candidate_count": len(scored),
                "above_floor": above,
                "top_score": round(top, 4),
                "mean_score": round(mean, 4),
                "floor_used": floor,
                "weights": _WEIGHTS,
            },
            subject_id=plan.trace_id,
        ))

    return scored
