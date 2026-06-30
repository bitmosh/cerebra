"""Phase 8 Step 3 — ContinuationBundle and BundleDistiller.

ContinuationBundle is a frozen distillation of a session's cognitive state,
created when a cycle triggers continuation. It primes the child session so it
can resume coherently without re-reading the full event history.

Phase 9 wires the Clutch continuation trigger and sophisticated distillers.
v0.1 ships the mechanism callable but not auto-invoked from any cycle.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ── helpers ───────────────────────────────────────────────────────────────────


def _now_ms() -> int:
    return int(time.time() * 1000)


def _generate_bundle_id() -> str:
    return f"bundle_{uuid.uuid4().hex[:12]}"


# ── ContinuationBundle ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ContinuationBundle:
    """Distilled session-state bundle for child-session priming.

    All JSON-serialized fields (truth_tower_projection, cognitive_insights,
    open_questions, constraints) are stored as dicts/lists in-memory and
    serialized to TEXT in SQLite via the persistence helpers.
    """

    bundle_id: str
    parent_session_id: str
    distilled_goal: str
    summarized_prior_prompt: str
    truth_tower_projection: dict[str, Any]  # JSON TEXT in DB
    cognitive_insights: list[str]            # JSON TEXT in DB
    next_focus: str
    open_questions: list[str]               # JSON TEXT in DB
    constraints: list[str]                  # JSON TEXT in DB
    recursion_depth: int
    voice_mode: str
    bundle_size_bytes: int
    created_at: int
    child_session_id: str | None = None
    triggered_at: int | None = None

    def to_prompt_prefix(self) -> str:
        """Render bundle fields as a structured prompt prefix for child session priming."""
        lines: list[str] = [
            f"## Continuation Context (depth {self.recursion_depth})",
            f"**Goal:** {self.distilled_goal}",
            f"**Prior summary:** {self.summarized_prior_prompt}",
            f"**Next focus:** {self.next_focus}",
        ]
        if self.cognitive_insights:
            lines.append("**Insights:**")
            for insight in self.cognitive_insights:
                lines.append(f"  - {insight}")
        if self.open_questions:
            lines.append("**Open questions:**")
            for q in self.open_questions:
                lines.append(f"  - {q}")
        if self.constraints:
            lines.append("**Constraints:**")
            for c in self.constraints:
                lines.append(f"  - {c}")
        return "\n".join(lines)

    @property
    def size_bytes(self) -> int:
        return self.bundle_size_bytes


# ── BundleDistiller ───────────────────────────────────────────────────────────


class BundleDistiller:
    """Distills a RuntimeSession's cognitive state into a ContinuationBundle.

    v0.1 stubs: each helper returns a minimal but structurally valid value.
    Phase 9 replaces stubs with LLM-driven summarization and tower projection.
    """

    def distill(
        self,
        parent_session_id: str,
        goal: str,
        recursion_depth: int,
        voice_mode: str = "default",
        step_outputs: list[str] | None = None,
        tower_data: dict[str, Any] | None = None,
    ) -> ContinuationBundle:
        """Create a ContinuationBundle from session context.

        Args:
            parent_session_id: Session being continued.
            goal: Original session goal (passed through).
            recursion_depth: Depth of this bundle's parent session.
            voice_mode: Cognitive voice mode for child session.
            step_outputs: Raw LLM outputs from completed steps (v0.1: for summary).
            tower_data: Truth tower snapshot (v0.1: passed through or empty).
        """
        distilled_goal = self._distill_goal(goal, step_outputs or [])
        summary = self._distill_summary(goal, step_outputs or [])
        projection = self._distill_tower_projection(tower_data or {})
        insights = self._distill_insights(step_outputs or [])
        next_focus = self._distill_next_focus(goal, step_outputs or [])
        open_questions = self._distill_open_questions(step_outputs or [])
        constraints = self._distill_constraints(step_outputs or [])

        # Compute size from serializable content
        raw = {
            "distilled_goal": distilled_goal,
            "summarized_prior_prompt": summary,
            "truth_tower_projection": projection,
            "cognitive_insights": insights,
            "next_focus": next_focus,
            "open_questions": open_questions,
            "constraints": constraints,
        }
        bundle_size_bytes = len(json.dumps(raw).encode())

        return ContinuationBundle(
            bundle_id=_generate_bundle_id(),
            parent_session_id=parent_session_id,
            distilled_goal=distilled_goal,
            summarized_prior_prompt=summary,
            truth_tower_projection=projection,
            cognitive_insights=insights,
            next_focus=next_focus,
            open_questions=open_questions,
            constraints=constraints,
            recursion_depth=recursion_depth,
            voice_mode=voice_mode,
            bundle_size_bytes=bundle_size_bytes,
            created_at=_now_ms(),
        )

    # ── v0.1 stub helpers (Phase 9 replaces these) ───────────────────────────

    def _distill_goal(self, goal: str, _step_outputs: list[str]) -> str:
        """v0.1: pass through the original goal unchanged."""
        return goal

    def _distill_summary(self, goal: str, step_outputs: list[str]) -> str:
        """v0.1: concatenate step outputs up to 500 chars; prefix with goal."""
        combined = " | ".join(step_outputs) if step_outputs else "(no prior steps)"
        raw = f"Goal: {goal}. Prior work: {combined}"
        return raw[:500]

    def _distill_tower_projection(self, tower_data: dict[str, Any]) -> dict[str, Any]:
        """v0.1: pass through tower snapshot; return empty dict if none."""
        return dict(tower_data) if tower_data else {}

    def _distill_insights(self, _step_outputs: list[str]) -> list[str]:
        """v0.1: no insights extracted (Phase 9 LLM call)."""
        return []

    def _distill_next_focus(self, goal: str, _step_outputs: list[str]) -> str:
        """v0.1: next focus is the original goal (Phase 9 refines from last step)."""
        return goal

    def _distill_open_questions(self, _step_outputs: list[str]) -> list[str]:
        """v0.1: no open questions extracted (Phase 9 LLM call)."""
        return []

    def _distill_constraints(self, _step_outputs: list[str]) -> list[str]:
        """v0.1: no constraints extracted (Phase 9 LLM call)."""
        return []


# ── Persistence helpers ───────────────────────────────────────────────────────


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def write_bundle(db_path: Path, bundle: ContinuationBundle) -> None:
    """Persist a ContinuationBundle to continuation_bundles table."""
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO continuation_bundles (
                bundle_id, parent_session_id, child_session_id,
                distilled_goal, summarized_prior_prompt,
                truth_tower_projection, cognitive_insights,
                next_focus, open_questions, constraints,
                recursion_depth, voice_mode, bundle_size_bytes,
                created_at, triggered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bundle.bundle_id,
                bundle.parent_session_id,
                bundle.child_session_id,
                bundle.distilled_goal,
                bundle.summarized_prior_prompt,
                json.dumps(bundle.truth_tower_projection),
                json.dumps(bundle.cognitive_insights),
                bundle.next_focus,
                json.dumps(bundle.open_questions),
                json.dumps(bundle.constraints),
                bundle.recursion_depth,
                bundle.voice_mode,
                bundle.bundle_size_bytes,
                bundle.created_at,
                bundle.triggered_at,
            ),
        )


def read_bundle(db_path: Path, bundle_id: str) -> ContinuationBundle | None:
    """Read a ContinuationBundle by ID. Returns None if not found."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM continuation_bundles WHERE bundle_id = ?", (bundle_id,)
        ).fetchone()
    if row is None:
        return None
    return _row_to_bundle(row)


def list_bundles_for_session(
    db_path: Path, parent_session_id: str
) -> list[ContinuationBundle]:
    """Return all bundles for a given parent session, ordered by created_at ASC."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM continuation_bundles WHERE parent_session_id = ? ORDER BY created_at ASC",
            (parent_session_id,),
        ).fetchall()
    return [_row_to_bundle(r) for r in rows]


def link_child_session(
    db_path: Path, bundle_id: str, child_session_id: str, triggered_at: int | None = None
) -> None:
    """Set child_session_id and optional triggered_at on an existing bundle."""
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE continuation_bundles SET child_session_id = ?, triggered_at = ? WHERE bundle_id = ?",
            (child_session_id, triggered_at or _now_ms(), bundle_id),
        )


def _row_to_bundle(row: tuple[Any, ...]) -> ContinuationBundle:
    (
        bundle_id, parent_session_id, child_session_id,
        distilled_goal, summarized_prior_prompt,
        truth_tower_projection_json, cognitive_insights_json,
        next_focus, open_questions_json, constraints_json,
        recursion_depth, voice_mode, bundle_size_bytes,
        created_at, triggered_at,
    ) = row
    return ContinuationBundle(
        bundle_id=bundle_id,
        parent_session_id=parent_session_id,
        child_session_id=child_session_id,
        distilled_goal=distilled_goal,
        summarized_prior_prompt=summarized_prior_prompt,
        truth_tower_projection=json.loads(truth_tower_projection_json),
        cognitive_insights=json.loads(cognitive_insights_json),
        next_focus=next_focus,
        open_questions=json.loads(open_questions_json),
        constraints=json.loads(constraints_json),
        recursion_depth=recursion_depth,
        voice_mode=voice_mode,
        bundle_size_bytes=bundle_size_bytes,
        created_at=created_at,
        triggered_at=triggered_at,
    )
