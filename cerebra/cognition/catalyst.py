"""CatalystEngine — Phase 9 Step 3.

Consumes the Bandit primitive (cerebra/_primitives/bandit.py) to provide
adaptive cognitive strategy selection within a cycle session.

Scoring formula (v0.1): base_reward × type_penalty × confidence_ramp
  base_reward     = arm's mean_reward from bandit state (0.5 default for fresh arms)
  type_penalty    = max(0.5, 1.0 - (recent_same_type_count × 0.15)) over K=5 window
  confidence_ramp = min(1.0, count / 5.0) — ramps to 1.0 after 5 selections

Arm selection:
  1. Unsampled arms are force-explored first (declaration order).
  2. Once all arms sampled, highest scoring arm wins (first-wins on ties).

Reward feedback: reward = composite_score × confidence (both from EvaluationPacket).
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cerebra._primitives import Bandit

if TYPE_CHECKING:
    from cerebra.cognition.cycle_config import CatalystArm

_TYPE_PRESSURE: float = 0.15
_TYPE_PENALTY_FLOOR: float = 0.5
_CONFIDENCE_RAMP_K: int = 5
_BASE_REWARD_DEFAULT: float = 0.5  # neutral prior for first selection (forced-explore)
_RECENT_WINDOW_K: int = 5


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class CatalystSelection:
    """Result of a single catalyst invocation."""

    arm_id: str
    arm_type: str
    mapped_action: str
    strategy_prompt: str
    selection_reason: str  # "forced_exploration" | "scored"
    score: float  # composite selection score (0 for forced_exploration)
    score_components: dict[str, float]


class CatalystEngine:
    """Session-scoped engine that selects cognitive strategy arms via bandit statistics.

    Usage:
        engine = CatalystEngine(session_id, db_path, arms)
        selection = engine.select(step_index=2)
        # ... run the step with selection.strategy_prompt ...
        engine.record_reward(selection.arm_id, reward=0.72, step_index=2)
    """

    def __init__(
        self,
        session_id: str,
        db_path: Path,
        arms: list[CatalystArm],
        parent_session_id: str | None = None,
    ) -> None:
        self._session_id = session_id
        self._db_path = db_path
        self._parent_session_id = parent_session_id
        self._arms = arms
        self._arm_map = {a.arm_id: a for a in arms}
        self._bandit = Bandit()
        self._selection_counter = self._load_selection_counter()
        if arms:
            self._bandit.ensure_arms([a.arm_id for a in arms])
            self._load_bandit_state()

    # ── Public API ────────────────────────────────────────────────────────────

    def select(self) -> CatalystSelection | None:
        """Select the best arm for the current step. Returns None if no arms declared."""
        if not self._arms:
            return None

        stats = {a.arm_id: self._bandit.get_stats(a.arm_id) for a in self._arms}
        unsampled = [a for a in self._arms if stats[a.arm_id].count == 0]

        if unsampled:
            arm = unsampled[0]
            return CatalystSelection(
                arm_id=arm.arm_id,
                arm_type=arm.type,
                mapped_action=arm.mapped_action,
                strategy_prompt=arm.strategy_prompt,
                selection_reason="forced_exploration",
                score=0.0,
                score_components={"base_reward": 0.0, "type_penalty": 1.0, "confidence_ramp": 0.0},
            )

        recent_types = self._load_recent_types()
        best_arm: CatalystArm | None = None
        best_score = -1.0
        best_components: dict[str, float] = {}

        for arm in self._arms:
            arm_stats = stats[arm.arm_id]
            base_reward = arm_stats.mean_reward if arm_stats.count > 0 else _BASE_REWARD_DEFAULT
            type_penalty = max(
                _TYPE_PENALTY_FLOOR,
                1.0 - (recent_types.count(arm.type) * _TYPE_PRESSURE),
            )
            confidence_ramp = min(1.0, arm_stats.count / _CONFIDENCE_RAMP_K)
            score = base_reward * type_penalty * confidence_ramp

            if score > best_score:
                best_score = score
                best_arm = arm
                best_components = {
                    "base_reward": round(base_reward, 4),
                    "type_penalty": round(type_penalty, 4),
                    "confidence_ramp": round(confidence_ramp, 4),
                }

        if best_arm is None:
            return None

        return CatalystSelection(
            arm_id=best_arm.arm_id,
            arm_type=best_arm.type,
            mapped_action=best_arm.mapped_action,
            strategy_prompt=best_arm.strategy_prompt,
            selection_reason="scored",
            score=round(best_score, 4),
            score_components=best_components,
        )

    def record_reward(self, arm_id: str, reward: float, step_index: int) -> None:
        """Update bandit state after observing the reward for the selected arm."""
        if arm_id not in self._arm_map:
            return
        self._bandit.update(arm_id, reward)
        self._selection_counter += 1
        self._save_bandit_state(arm_id, step_index)
        self._append_recent_selection(arm_id)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _fetch_arm_stats(self, session_id: str) -> list[Any]:
        """Fetch catalyst_arm_stats rows for a session_id. Returns [] on any error."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(
                "SELECT arm_id, count, total_reward, last_selected_step "
                "FROM catalyst_arm_stats WHERE runtime_session_id = ?",
                (session_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    def _load_bandit_state(self) -> None:
        """Restore arm stats from catalyst_arm_stats table.

        Tries own session_id first; falls back to parent_session_id for child
        sessions inheriting arm stats at spawn time (S4-D2).
        """
        rows = self._fetch_arm_stats(self._session_id)
        if not rows and self._parent_session_id:
            rows = self._fetch_arm_stats(self._parent_session_id)

        if not rows:
            return

        arms_data = {
            row["arm_id"]: {
                "count": row["count"],
                "total_reward": row["total_reward"],
                "last_selected_step": row["last_selected_step"],
            }
            for row in rows
        }
        state = {"exploration_weight": 1.4, "arms": arms_data}
        self._bandit = Bandit.from_state(state)

    def _save_bandit_state(self, updated_arm_id: str, step_index: int) -> None:
        """Upsert the updated arm's stats into catalyst_arm_stats."""
        arm_stats = self._bandit.get_stats(updated_arm_id)
        now = _now_ms()
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                """
                INSERT INTO catalyst_arm_stats
                    (arm_id, runtime_session_id, count, total_reward,
                     last_selected_step, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (arm_id, runtime_session_id) DO UPDATE SET
                    count = excluded.count,
                    total_reward = excluded.total_reward,
                    last_selected_step = excluded.last_selected_step,
                    updated_at = excluded.updated_at
                """,
                (
                    updated_arm_id,
                    self._session_id,
                    arm_stats.count,
                    arm_stats.total_reward,
                    step_index,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _load_selection_counter(self) -> int:
        """Return the current max selection_order for this session (0 if none)."""
        conn = sqlite3.connect(self._db_path)
        try:
            row = conn.execute(
                "SELECT MAX(selection_order) FROM catalyst_recent_selections "
                "WHERE runtime_session_id = ?",
                (self._session_id,),
            ).fetchone()
            return (row[0] or 0) if row else 0
        except sqlite3.OperationalError:
            return 0
        finally:
            conn.close()

    def _append_recent_selection(self, arm_id: str) -> None:
        """Insert a row into catalyst_recent_selections for type_penalty tracking."""
        arm = self._arm_map.get(arm_id)
        if arm is None:
            return
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO catalyst_recent_selections
                    (runtime_session_id, selection_order, arm_id, arm_type, selected_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self._session_id, self._selection_counter, arm_id, arm.type, _now_ms()),
            )
            conn.commit()
        finally:
            conn.close()

    def _load_recent_types(self) -> list[str]:
        """Return the last K arm types selected in this session (oldest-first)."""
        conn = sqlite3.connect(self._db_path)
        try:
            rows = conn.execute(
                """
                SELECT arm_type FROM catalyst_recent_selections
                WHERE runtime_session_id = ?
                ORDER BY selection_order DESC
                LIMIT ?
                """,
                (self._session_id, _RECENT_WINDOW_K),
            ).fetchall()
            return [row[0] for row in rows]
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()
