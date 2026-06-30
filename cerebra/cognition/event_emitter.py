"""
EventEmitter — Cerebra-layer wrapper around FossicStore.append.

Handles:
- Automatic stream naming (cerebra/agent-trace/<cycle_id> and cerebra/lattice/<lineage_id>)
- Implicit causation chaining: each cycle event defaults causation_id to the
  previous cycle event's ID, making the cycle trace a causation chain.
- Snapshot triggering at cycle boundaries for lattice streams.
"""

from __future__ import annotations

from typing import Any

from cerebra.cognition._constants import LATTICE_SNAPSHOT_CADENCE
from cerebra.storage.fossic_store import FossicStore


class EventEmitter:
    """Emits events to fossic streams for a single session+cycle context."""

    def __init__(self, store: FossicStore, session_id: str, cycle_id: str) -> None:
        self.store = store
        self.session_id = session_id
        self.cycle_id = cycle_id
        self._last_event_id: bytes | None = None

    def emit_cycle_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        causation_id: bytes | None = None,
        indexed_tags: dict[str, Any] | None = None,
    ) -> bytes:
        """Emit an event on cerebra/agent-trace/<session_id>.

        If causation_id is None, the previous cycle event's ID is used, making
        the full cycle trace a causation chain without caller bookkeeping.
        """
        stream_id = f"cerebra/agent-trace/{self.session_id}"
        eid = self.store.append(
            stream_id=stream_id,
            event_type=event_type,
            payload=payload,
            causation_id=causation_id if causation_id is not None else self._last_event_id,
            indexed_tags=indexed_tags,
        )
        self._last_event_id = eid
        return eid

    def emit_lattice_event(
        self,
        lineage_id: str,
        event_type: str,
        payload: dict[str, Any],
        causation_id: bytes | None = None,
        indexed_tags: dict[str, Any] | None = None,
    ) -> bytes:
        """Emit an event on cerebra/lattice/<lineage_id>.

        Causation is not auto-chained for lattice events — callers own the
        causation chain across lineages.
        """
        stream_id = f"cerebra/lattice/{lineage_id}"
        return self.store.append(
            stream_id=stream_id,
            event_type=event_type,
            payload=payload,
            causation_id=causation_id,
            indexed_tags=indexed_tags,
        )

    def trigger_lattice_snapshots_at_cycle_boundary(
        self, touched_lineages: set[str]
    ) -> None:
        """At CycleCompleted, snapshot lattice streams that have accumulated
        >= LATTICE_SNAPSHOT_CADENCE events since their last snapshot.

        Called by the cycle runtime after emitting CycleCompleted. Silently
        skips streams that haven't reached the threshold or have no events.
        """
        for lineage_id in touched_lineages:
            stream_id = f"cerebra/lattice/{lineage_id}"
            current = self.store.current_version(stream_id)
            last_snapshot = self.store.last_snapshot_version(stream_id)
            if current - last_snapshot >= LATTICE_SNAPSHOT_CADENCE:
                self.store.take_snapshot(stream_id)
