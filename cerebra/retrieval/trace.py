"""
Retrieval trace writer — persists query audit rows to Migration008 tables.

Three tables, written atomically in one transaction:
  retrieval_traces      — one row per query (plan summary, timing, counts)
  retrieval_steps       — one row per traversal step (from TraversalStepCompleted events)
  retrieval_candidates  — one row per scored candidate (score JSON, selected flag)

Usage:
  trace_data = TraceData(plan, scored_all, floor, started_at, finished_at,
                         duration_ms, step_events)
  write_trace(trace_data, db_path, event_log=log)  # raises on failure

context_packet_id is always NULL in Phase 4 Step 7; Step 8 sets it.

See docs/agent/plans/v01_phase4_design.md §5.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from cerebra.inspector.event import make_event
from cerebra.inspector.sqlite_log import SQLiteEventLog
from cerebra.retrieval.planner import QueryPlan
from cerebra.retrieval.scorer import ScoredCandidate
from cerebra.storage.db import connect


@dataclass
class TraceData:
    """All data needed to write a complete retrieval trace.

    Constructed by the CLI after the full planner → traversal → scorer pipeline.

    Attributes:
        plan:         The QueryPlan produced by query_plan().
        scored_all:   All ScoredCandidates returned by score_candidates() (pre-floor).
        floor:        The relevance floor used to distinguish selected vs excluded.
        started_at:   Epoch seconds when the query pipeline began.
        finished_at:  Epoch seconds when scoring completed.
        duration_ms:  Wall-clock ms from monotonic clock (more precise than
                      finished_at - started_at when both are in seconds).
        step_events:  List of data dicts from TraversalStepCompleted inspector events
                      (parsed from data_json). One dict per traversal step.
    """

    plan: QueryPlan
    scored_all: list[ScoredCandidate]
    floor: float
    started_at: int
    finished_at: int
    duration_ms: int
    step_events: list[dict] = field(default_factory=list)


def write_trace(
    trace_data: TraceData,
    db_path: Path,
    *,
    event_log: SQLiteEventLog | None = None,
) -> str:
    """Persist retrieval_traces, retrieval_steps, and retrieval_candidates rows.

    All three tables are written in a single transaction. On any error, the
    transaction rolls back and the exception propagates to the caller (CLI exits 2).

    Returns the trace_id on success.
    Emits TraceWritten inspector event when event_log is provided.
    """
    t_write_start = time.monotonic_ns()

    plan = trace_data.plan
    scored = trace_data.scored_all
    trace_id = plan.trace_id

    above_floor_ids = {c.record_id for c in scored if c.score.composite >= trace_data.floor}
    selected_count = len(above_floor_ids)
    abstained = 1 if selected_count == 0 else 0

    plan_json = json.dumps(
        {
            "trace_id": plan.trace_id,
            "raw_query": plan.raw_query,
            "query_d1": plan.query_d1,
            "query_d1_d2_d3": plan.query_d1_d2_d3,
            "mode": plan.mode,
            "max_candidates": plan.max_candidates,
            "staleness_warnings": plan.staleness_warnings,
        }
    )

    with connect(db_path) as conn:
        # ── retrieval_traces: one row ─────────────────────────────────────────
        conn.execute(
            """
            INSERT INTO retrieval_traces (
                trace_id, query, mode, query_sku_d1, query_sku_pattern,
                plan_json, started_at, finished_at, duration_ms,
                candidate_count, selected_count, abstained,
                context_packet_id, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 1)
            """,
            (
                trace_id,
                plan.raw_query,
                plan.mode,
                plan.query_d1,
                plan.query_d1_d2_d3,
                plan_json,
                trace_data.started_at,
                trace_data.finished_at,
                trace_data.duration_ms,
                len(scored),
                selected_count,
                abstained,
            ),
        )

        # ── retrieval_steps: one row per traversal step ───────────────────────
        for evt in trace_data.step_events:
            step_name = evt.get("step_name", "unknown")
            step_id = f"{trace_id}_step_{step_name}"
            conn.execute(
                """
                INSERT INTO retrieval_steps (
                    step_id, trace_id, step_number, step_name,
                    candidate_count, new_candidates, duration_ms,
                    skipped, skip_reason, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    step_id,
                    trace_id,
                    evt.get("step_number", 0),
                    step_name,
                    evt.get("candidate_count", 0),
                    evt.get("new_candidates", 0),
                    evt.get("duration_ms", 0),
                    1 if evt.get("skipped") else 0,
                    evt.get("skip_reason"),
                ),
            )

        # ── retrieval_candidates: one row per scored candidate ────────────────
        for c in scored:
            candidate_id = f"cand_{trace_id}_{c.record_id}"
            selected = 1 if c.record_id in above_floor_ids else 0
            exclusion_reason = None if selected else "below_floor"
            score_json = json.dumps(
                {
                    "composite": c.score.composite,
                    "components": c.score.components,
                    "weights": c.score.weights,
                }
            )
            conn.execute(
                """
                INSERT INTO retrieval_candidates (
                    candidate_id, trace_id, record_id, step_surfaced,
                    retrieval_path, salience_score, score_json,
                    selected, rank, exclusion_reason, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    candidate_id,
                    trace_id,
                    c.record_id,
                    c.step_surfaced,
                    c.retrieval_path,
                    round(c.score.composite, 6),
                    score_json,
                    selected,
                    c.rank if selected else None,
                    exclusion_reason,
                ),
            )

    write_duration_ms = max(0, (time.monotonic_ns() - t_write_start) // 1_000_000)

    if event_log is not None:
        event_log.write(
            make_event(
                event_type="TraceWritten",
                actor="retrieval.trace",
                summary=f"Trace written: {trace_id}, {len(scored)} candidates, {selected_count} selected",
                data={
                    "trace_id": trace_id,
                    "candidate_count": len(scored),
                    "selected_count": selected_count,
                    "duration_ms": write_duration_ms,
                },
                subject_id=trace_id,
            )
        )

    return trace_id
