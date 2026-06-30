"""
Six-step SKU traversal — reads candidates from the database, no scoring.

Steps:
  1. Query SKU construction (build query_sku_pattern from plan.query_d1)
  2. Exact SKU match (sku_address LIKE 'pattern%')
  3. Partial SKU match (d1 = query_d1)
  4. Sibling pointer traversal (no-op in v0.1.x; placeholder for v0.2+)
  5. Retrieval: lexical search and/or vector fallback based on mode
  6. Trace annotation (assemble retrieval_path for each candidate)

All six steps run for every query. Empty steps fall through silently.
`run_traversal()` returns a flat list[RawCandidate] — caller scores.

Multi-commit compatibility: the interface uses list[str] record_ids, not
1:1 record-to-SKU, so the interpretive lattice (v0.2+) can return multiple
record IDs per chunk without changing this module's interface.

See docs/agent/plans/v01_phase4_design.md §3.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from cerebra.inspector.event import make_event
from cerebra.inspector.sqlite_log import SQLiteEventLog
from cerebra.retrieval.planner import QueryPlan
from cerebra.storage.db import connect
from cerebra.storage.lexical import search as lexical_search


@dataclass
class RawCandidate:
    """A candidate record gathered by the traversal — unscored.

    `step_surfaced` is the first step that found this record.
    `retrieval_path` is assembled in Step 6 from all steps that touched it.
    `semantic_score` is set if the record appeared in cosine_search results.
    `lexical_score` is set if the record appeared in lexical search results.
    `sku_d1_match` is True if the record's D1 matches the query's D1.
    """

    record_id: str
    step_surfaced: str
    retrieval_path: str
    semantic_score: float | None
    lexical_score: float | None
    sku_d1_match: bool
    _steps: list[str] = field(default_factory=list, repr=False, compare=False)


# ── Step helpers ───────────────────────────────────────────────────────────────


def _step1_construct_sku_query(plan: QueryPlan) -> tuple[int | None, str | None]:
    """Step 1: derive query_sku_d1 and query_sku_pattern from the plan."""
    if plan.query_d1 is None:
        return None, None
    return plan.query_d1, f"0x{plan.query_d1:x}"


def _step2_exact_sku(
    query_sku_pattern: str | None,
    db_path: Path,
) -> list[str]:
    """Step 2: exact SKU match — records whose sku_address starts with the D1 pattern."""
    if query_sku_pattern is None:
        return []
    pattern = f"{query_sku_pattern}%"
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT sa.record_id
              FROM sku_assignments sa
              JOIN memory_records m ON sa.record_id = m.record_id
             WHERE sa.sku_address LIKE ?
               AND m.lifecycle_state = 'active'
            """,
            (pattern,),
        ).fetchall()
    return [row["record_id"] for row in rows]


def _step3_partial_sku(
    query_d1: int | None,
    db_path: Path,
    seen_ids: set[str],
) -> list[str]:
    """Step 3: partial SKU match — all active records with matching D1 digit."""
    if query_d1 is None:
        return []
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT sa.record_id
              FROM sku_assignments sa
              JOIN memory_records m ON sa.record_id = m.record_id
             WHERE sa.d1 = ?
               AND m.lifecycle_state = 'active'
            """,
            (query_d1,),
        ).fetchall()
    return [row["record_id"] for row in rows if row["record_id"] not in seen_ids]


def traverse_siblings(candidate_ids: list[str], db_path: Path) -> list[str]:
    """Step 4: sibling pointer traversal.

    Phase 4 no-op: every record has at most one SKU address (single-pointer v0.1).
    Multi-pointer fanout is a v0.2+ concern (interpretive lattice).
    Returns the input list unchanged.
    """
    return candidate_ids


def _step5_lexical(
    query: str,
    db_path: Path,
    max_candidates: int,
) -> list[tuple[str, float]]:
    """Run FTS5 BM25 lexical search. Returns (record_id, rank) pairs."""
    return lexical_search(db_path, query, limit=max_candidates)


def _step5_vector(
    query: str,
    db_path: Path,
    max_candidates: int,
) -> list[tuple[str, float]]:
    """Run unrestricted cosine vector search. Returns (record_id, score) pairs.

    Returns [] if numpy or the embeddings table is unavailable.
    """
    try:
        from cerebra.storage.embeddings import cosine_search, embed
    except ImportError:
        return []

    try:
        query_vec = embed([query])[0]
        return cosine_search(db_path, query_vec, limit=max_candidates)
    except Exception:
        return []


# ── Step 6 helper ──────────────────────────────────────────────────────────────


def _assemble_retrieval_path(
    record_id: str,
    steps: list[str],
    query_d1: int | None,
) -> str:
    """Build a human-readable retrieval_path from the steps that found a record.

    Examples:
      "exact_sku:D1=0x5"
      "partial_sku:D1=0x5"
      "vector_fallback"
      "exact_sku:D1=0x5 + vector_fallback"
      "lexical_search + vector_fallback"
    """
    parts = []
    d1_tag = f"D1=0x{query_d1:x}" if query_d1 is not None else ""

    for step in steps:
        if step == "exact_sku":
            parts.append(f"exact_sku:{d1_tag}" if d1_tag else "exact_sku")
        elif step == "partial_sku":
            parts.append(f"partial_sku:{d1_tag}" if d1_tag else "partial_sku")
        elif step == "lexical_search":
            parts.append("lexical_search")
        elif step == "vector_fallback":
            parts.append("vector_fallback")
        else:
            parts.append(step)

    return " + ".join(parts) if parts else "unknown"


# ── Main traversal ─────────────────────────────────────────────────────────────


def _emit_step(
    event_log: SQLiteEventLog | None,
    trace_id: str,
    step_number: int,
    step_name: str,
    candidate_count: int,
    new_candidates: int,
    duration_ms: int,
    skipped: bool = False,
    skip_reason: str | None = None,
) -> None:
    if event_log is None:
        return
    event_log.write(make_event(
        event_type="TraversalStepCompleted",
        actor="retrieval.traversal",
        summary=f"Step {step_number} {step_name}: {candidate_count} candidates",
        data={
            "trace_id": trace_id,
            "step_number": step_number,
            "step_name": step_name,
            "candidate_count": candidate_count,
            "new_candidates": new_candidates,
            "duration_ms": duration_ms,
            "skipped": skipped,
            "skip_reason": skip_reason,
        },
        subject_id=trace_id,
    ))


def run_traversal(
    plan: QueryPlan,
    db_path: Path,
    *,
    event_log: SQLiteEventLog | None = None,
) -> list[RawCandidate]:
    """Execute the six-step SKU traversal and return raw (unscored) candidates.

    Mode determines which retrieval signals are active:
      hybrid       — SKU steps + lexical + vector
      lexical_only — SKU steps + lexical (no vector)
      vector_only  — SKU steps + vector (no lexical)

    All six steps execute for every call; empty steps produce no candidates.
    The candidate set is capped at plan.max_candidates.
    """
    trace_id = plan.trace_id
    mode = plan.mode

    # Accumulator: record_id → {step_name, lexical_score, semantic_score, steps_list}
    # First occurrence of a record_id wins `step_surfaced`.
    candidates: dict[str, dict] = {}

    def _add(
        record_id: str,
        step: str,
        lexical_score: float | None = None,
        semantic_score: float | None = None,
        sku_d1_match: bool = False,
    ) -> bool:
        """Add or update a candidate. Returns True if this was a new addition."""
        if record_id not in candidates:
            candidates[record_id] = {
                "step_surfaced": step,
                "steps": [step],
                "lexical_score": lexical_score,
                "semantic_score": semantic_score,
                "sku_d1_match": sku_d1_match,
            }
            return True
        else:
            entry = candidates[record_id]
            if step not in entry["steps"]:
                entry["steps"].append(step)
            if lexical_score is not None:
                entry["lexical_score"] = lexical_score
            if semantic_score is not None:
                entry["semantic_score"] = semantic_score
            if sku_d1_match:
                entry["sku_d1_match"] = True
            return False

    # ── Step 1: Query SKU construction ────────────────────────────────────────
    t0 = time.monotonic_ns()
    query_d1, query_sku_pattern = _step1_construct_sku_query(plan)
    _emit_step(
        event_log, trace_id,
        step_number=1, step_name="query_sku_construction",
        candidate_count=0, new_candidates=0,
        duration_ms=max(0, (time.monotonic_ns() - t0) // 1_000_000),
    )

    # ── Step 2: Exact SKU match ───────────────────────────────────────────────
    t0 = time.monotonic_ns()
    before = len(candidates)
    exact_ids = _step2_exact_sku(query_sku_pattern, db_path)
    for rid in exact_ids:
        _add(rid, "exact_sku", sku_d1_match=True)
    _emit_step(
        event_log, trace_id,
        step_number=2, step_name="exact_sku",
        candidate_count=len(candidates), new_candidates=len(candidates) - before,
        duration_ms=max(0, (time.monotonic_ns() - t0) // 1_000_000),
    )

    # ── Step 3: Partial SKU match ─────────────────────────────────────────────
    t0 = time.monotonic_ns()
    before = len(candidates)
    partial_ids = _step3_partial_sku(query_d1, db_path, seen_ids=set(candidates))
    for rid in partial_ids:
        _add(rid, "partial_sku", sku_d1_match=True)
    _emit_step(
        event_log, trace_id,
        step_number=3, step_name="partial_sku",
        candidate_count=len(candidates), new_candidates=len(candidates) - before,
        duration_ms=max(0, (time.monotonic_ns() - t0) // 1_000_000),
    )

    # ── Step 4: Sibling traversal (no-op) ─────────────────────────────────────
    t0 = time.monotonic_ns()
    # No-op: Step 4 is a placeholder for v0.2+ multi-pointer fanout.
    _emit_step(
        event_log, trace_id,
        step_number=4, step_name="sibling_traversal",
        candidate_count=len(candidates), new_candidates=0,
        duration_ms=max(0, (time.monotonic_ns() - t0) // 1_000_000),
        skipped=True, skip_reason="single-pointer v0.1",
    )

    # ── Step 5a: Lexical search ───────────────────────────────────────────────
    if mode in ("hybrid", "lexical_only"):
        t0 = time.monotonic_ns()
        before = len(candidates)
        lex_results = _step5_lexical(plan.raw_query, db_path, plan.max_candidates)
        for rid, rank in lex_results:
            _add(rid, "lexical_search", lexical_score=rank)
        _emit_step(
            event_log, trace_id,
            step_number=5, step_name="lexical_search",
            candidate_count=len(candidates), new_candidates=len(candidates) - before,
            duration_ms=max(0, (time.monotonic_ns() - t0) // 1_000_000),
        )

    # ── Step 5b: Vector fallback ──────────────────────────────────────────────
    if mode in ("hybrid", "vector_only"):
        t0 = time.monotonic_ns()
        before = len(candidates)
        vec_results = _step5_vector(plan.raw_query, db_path, plan.max_candidates)
        for rid, score in vec_results:
            _add(rid, "vector_fallback", semantic_score=score)
        _emit_step(
            event_log, trace_id,
            step_number=5, step_name="vector_fallback",
            candidate_count=len(candidates), new_candidates=len(candidates) - before,
            duration_ms=max(0, (time.monotonic_ns() - t0) // 1_000_000),
            skipped=(len(vec_results) == 0 and not vec_results),
        )

    # ── Step 6: Trace annotation — assemble retrieval_path ────────────────────
    t0 = time.monotonic_ns()
    raw = []
    for rid, entry in candidates.items():
        path = _assemble_retrieval_path(rid, entry["steps"], query_d1)
        raw.append(RawCandidate(
            record_id=rid,
            step_surfaced=entry["step_surfaced"],
            retrieval_path=path,
            semantic_score=entry["semantic_score"],
            lexical_score=entry["lexical_score"],
            sku_d1_match=entry["sku_d1_match"],
            _steps=entry["steps"],
        ))

    # Cap and sort: prefer highest semantic_score, then lexical_score
    raw.sort(key=lambda c: (
        c.semantic_score if c.semantic_score is not None else -1.0,
        abs(c.lexical_score) if c.lexical_score is not None else 0.0,
    ), reverse=True)
    raw = raw[: plan.max_candidates]

    _emit_step(
        event_log, trace_id,
        step_number=6, step_name="trace_annotation",
        candidate_count=len(raw), new_candidates=0,
        duration_ms=max(0, (time.monotonic_ns() - t0) // 1_000_000),
    )

    return raw
