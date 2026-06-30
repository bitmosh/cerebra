"""Phase 8 — RuntimeSession, SessionState, SessionManager, and persistence.

Stream pattern for session-level events (DEV-012):
  session_id IS the cycle_id segment → cerebra/agent-trace/<session_id>
  Per vocabulary spec: "session_id: str — UUID, also the stream's cycle_id segment"

SessionFlushed event is emitted by CycleRuntime (not SessionManager) because
the causation chain runs through CycleCompleted on the cycle's event stream.
flush_session() is a DB-only state transition.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from cerebra.cognition._constants import RECURSION_DEPTH_DEFAULT
from cerebra.cognition.event_emitter import EventEmitter
from cerebra.cognition.predictions import PredictionInput, read_outcomes_for_session
from cerebra.storage.fossic_store import FossicStore

# ── helpers ───────────────────────────────────────────────────────────────────


def _now_ms() -> int:
    return int(time.time() * 1000)


def _generate_session_id() -> str:
    return f"sess_{uuid.uuid4().hex[:12]}"


# ── dataclasses ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RuntimeSession:
    """Immutable session record. Mutations go through SessionManager."""

    session_id: str
    cycle_config: str
    goal: str
    vault_path: Path
    opened_at: int
    parent_session_id: str | None = None
    recursion_depth: int = 0
    max_recursion_depth: int = RECURSION_DEPTH_DEFAULT
    cycles_run: int = 0
    steps_run: int = 0
    state: str = "active"  # "active" | "flushed" | "continued"
    flushed_at: int | None = None
    final_outcome: str | None = None

    @property
    def is_active(self) -> bool:
        return self.state == "active"

    @property
    def can_recurse(self) -> bool:
        return self.recursion_depth < self.max_recursion_depth


@dataclass(frozen=True)
class SessionState:
    """Read-only view of session state for cycle runtime consumption (Step 2+).

    Bridges RuntimeSession with cycle-level context that changes as steps run.
    """

    session: RuntimeSession
    cycle_config_loaded: dict[str, Any]  # CycleConfig type arrives in Step 2
    prior_step_composites: list[float] = field(default_factory=list)
    prior_step_per_signal: dict[str, float] | None = None


# ── persistence helpers ───────────────────────────────────────────────────────


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def write_session(db_path: Path, session: RuntimeSession) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO runtime_sessions
                (session_id, cycle_config, goal, vault_path, opened_at,
                 parent_session_id, recursion_depth, max_recursion_depth,
                 cycles_run, steps_run, state, flushed_at, final_outcome)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.session_id,
                session.cycle_config,
                session.goal,
                str(session.vault_path),
                session.opened_at,
                session.parent_session_id,
                session.recursion_depth,
                session.max_recursion_depth,
                session.cycles_run,
                session.steps_run,
                session.state,
                session.flushed_at,
                session.final_outcome,
            ),
        )


def update_session_state(db_path: Path, session: RuntimeSession) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE runtime_sessions SET
                state = ?, flushed_at = ?, final_outcome = ?,
                cycles_run = ?, steps_run = ?
            WHERE session_id = ?
            """,
            (
                session.state,
                session.flushed_at,
                session.final_outcome,
                session.cycles_run,
                session.steps_run,
                session.session_id,
            ),
        )


def read_session(db_path: Path, session_id: str) -> RuntimeSession | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM runtime_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    if row is None:
        return None
    return _row_to_session(row)


def list_sessions_for_vault(
    db_path: Path,
    vault_path: Path,
    state: str | None = None,
) -> list[RuntimeSession]:
    with _connect(db_path) as conn:
        if state is not None:
            rows = conn.execute(
                "SELECT * FROM runtime_sessions WHERE vault_path = ? AND state = ? ORDER BY opened_at ASC",
                (str(vault_path), state),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM runtime_sessions WHERE vault_path = ? ORDER BY opened_at ASC",
                (str(vault_path),),
            ).fetchall()
    return [_row_to_session(r) for r in rows]


def list_continuation_chain(db_path: Path, root_session_id: str) -> list[RuntimeSession]:
    """Return the re-injection chain: root → child → grandchild in order."""
    result: list[RuntimeSession] = []
    current_id: str | None = root_session_id
    with _connect(db_path) as conn:
        while current_id is not None:
            row = conn.execute(
                "SELECT * FROM runtime_sessions WHERE session_id = ?", (current_id,)
            ).fetchone()
            if row is None:
                break
            session = _row_to_session(row)
            result.append(session)
            child_row = conn.execute(
                "SELECT session_id FROM runtime_sessions WHERE parent_session_id = ? LIMIT 1",
                (current_id,),
            ).fetchone()
            current_id = child_row[0] if child_row else None
    return result


def _row_to_session(row: tuple[Any, ...]) -> RuntimeSession:
    (
        session_id, cycle_config, goal, vault_path, opened_at,
        parent_session_id, recursion_depth, max_recursion_depth,
        cycles_run, steps_run, state, flushed_at, final_outcome,
    ) = row
    return RuntimeSession(
        session_id=session_id,
        cycle_config=cycle_config,
        goal=goal,
        vault_path=Path(vault_path),
        opened_at=opened_at,
        parent_session_id=parent_session_id,
        recursion_depth=recursion_depth,
        max_recursion_depth=max_recursion_depth,
        cycles_run=cycles_run,
        steps_run=steps_run,
        state=state,
        flushed_at=flushed_at,
        final_outcome=final_outcome,
    )


# ── PredictionInput adapter ───────────────────────────────────────────────────


def predict_input_from_session(
    session_state: SessionState,
    cycle_id: str,
    step_id: str,
) -> PredictionInput:
    """Bridge SessionState to Phase 6 Step 3's PredictionPipeline.

    Zero changes to PredictionPipeline. cycle_config_defaults is None in Step 1;
    Step 2 populates it from the loaded CycleConfig.
    """
    return PredictionInput(
        session_id=session_state.session.session_id,
        cycle_id=cycle_id,
        step_id=step_id,
        prior_step_composites=session_state.prior_step_composites,
        prior_step_per_signal=session_state.prior_step_per_signal,
        cycle_config_defaults=None,  # Step 2 fills this from CycleConfig
    )


# ── SessionManager ────────────────────────────────────────────────────────────


class SessionManager:
    """Manages RuntimeSession lifecycle: open, flush, read, and state projection."""

    def __init__(self, db_path: Path, store: FossicStore) -> None:
        self.db_path = db_path
        self.store = store

    def open_session(
        self,
        goal: str,
        cycle_config: str,
        vault_path: Path,
        parent_session_id: str | None = None,
    ) -> tuple[RuntimeSession, bytes]:
        """Create a new session, persist it, and emit SessionOpened.

        Returns:
            (RuntimeSession, opened_event_id) — the event_id is the fossic bytes ID
            of the SessionOpened event. CycleRuntime uses it as causation_id for
            CycleStarted, restoring the full cross-stream causation chain (DEV-018).

        Stream pattern (DEV-012): session_id IS the cycle_id segment.
        EventEmitter constructed with cycle_id=session_id.
        Causation: None — SessionOpened is the root event of the session stream.
        """
        recursion_depth = 0
        if parent_session_id is not None:
            parent = read_session(self.db_path, parent_session_id)
            if parent is None:
                raise ValueError(f"Parent session not found: {parent_session_id}")
            if not parent.can_recurse:
                raise ValueError(
                    f"Parent session {parent_session_id} has reached max recursion depth "
                    f"({parent.max_recursion_depth})"
                )
            recursion_depth = parent.recursion_depth + 1

        session_id = _generate_session_id()
        session = RuntimeSession(
            session_id=session_id,
            cycle_config=cycle_config,
            goal=goal,
            vault_path=vault_path,
            opened_at=_now_ms(),
            parent_session_id=parent_session_id,
            recursion_depth=recursion_depth,
        )
        write_session(self.db_path, session)

        # Emit SessionOpened — root event, causation_id=None (DEV-012)
        emitter = EventEmitter(
            store=self.store,
            session_id=session_id,
            cycle_id=session_id,  # session_id IS the stream segment per vocabulary spec
        )
        opened_event_id = emitter.emit_cycle_event(
            event_type="SessionOpened",
            payload={
                "session_id": session_id,
                "goal": goal,
                "cycle_config": cycle_config,
                "vault_path": str(vault_path),
                "opened_at": session.opened_at,
                "parent_session_id": parent_session_id,
                "recursion_depth": recursion_depth,
                "max_recursion_depth": session.max_recursion_depth,
            },
            indexed_tags={
                "cycle_config": cycle_config,
                "recursion_depth": str(recursion_depth),
                "parent_session_id": parent_session_id or "",
            },
        )

        return session, opened_event_id

    def flush_session(
        self,
        session_id: str,
        outcome: str,
        total_cycles: int,
        total_steps: int,
    ) -> RuntimeSession:
        """Mark session as flushed, update SQLite, return updated session.

        DB-only: SessionFlushed fossic event is emitted by CycleRuntime
        (it owns the causation chain via CycleCompleted).
        """
        session = read_session(self.db_path, session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        if not session.is_active:
            raise ValueError(
                f"Session {session_id} is not active (state={session.state!r})"
            )

        flushed = replace(
            session,
            state="flushed",
            flushed_at=_now_ms(),
            final_outcome=outcome,
            cycles_run=total_cycles,
            steps_run=total_steps,
        )
        update_session_state(self.db_path, flushed)
        return flushed

    def read_session(self, session_id: str) -> RuntimeSession | None:
        return read_session(self.db_path, session_id)

    def build_session_state(self, session_id: str) -> SessionState:
        """Build SessionState for cycle runtime consumption (Step 2+)."""
        session = read_session(self.db_path, session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        cycle_config_loaded = self._load_cycle_config(session.cycle_config)
        prior_composites, prior_per_signal = self._load_prior_step_trajectory(session_id)
        return SessionState(
            session=session,
            cycle_config_loaded=cycle_config_loaded,
            prior_step_composites=prior_composites,
            prior_step_per_signal=prior_per_signal,
        )

    def _load_cycle_config(self, name: str) -> dict[str, Any]:
        """Load cycle config YAML and return as raw dict for SessionState.

        Searches vault's cycles/ (db_path.parent.parent/cycles), then built-in.
        Returns {} if config not found (graceful fallback; CycleRuntime uses
        CycleConfigLoader directly for a typed CycleConfig object).
        """
        import dataclasses

        from cerebra.cognition.cycle_config import CycleConfigLoader

        vault_path = self.db_path.parent.parent
        try:
            loader = CycleConfigLoader()
            config = loader.load(name, vault_path)
            return dataclasses.asdict(config)
        except (FileNotFoundError, Exception):
            return {}

    def _load_prior_step_trajectory(
        self, session_id: str
    ) -> tuple[list[float], dict[str, float] | None]:
        """Load composite trajectory from outcomes table for this session."""
        outcomes = read_outcomes_for_session(self.db_path, session_id)
        if not outcomes:
            return [], None
        composites = [o.actual_composite_score for o in outcomes]
        # Per-signal trajectory: Step 2 wires this when evaluation packets are
        # available in cycle context. Step 1 returns None for the per-signal view.
        return composites, None
