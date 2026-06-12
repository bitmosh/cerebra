"""Integration test: FossicStore + EventEmitter snapshot lifecycle.

Tests the full 100-event cadence scenario against a real fossic store on disk.
This is the canonical proof that the snapshot trigger works end-to-end.

CCE note: fossic deduplicates events with identical content. All append loops use
unique payloads ({"_i": absolute_index}) to prevent deduplication collapsing the
event count.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cerebra.cognition._constants import LATTICE_SNAPSHOT_CADENCE
from cerebra.cognition.event_emitter import EventEmitter
from cerebra.storage.fossic_store import FossicStore


class _IdentityReducer:
    """Aggregates all payloads into a list — simple and deterministic."""

    name = "identity_reducer"
    version = 1
    state_schema_version = 1

    def initial_state(self) -> dict[str, list[Any]]:
        return {"items": []}

    def apply(
        self, state: dict[str, list[Any]], payload: Any
    ) -> dict[str, list[Any]]:
        return {"items": state["items"] + [payload]}


@pytest.mark.integration
class TestFossicSnapshotLifecycleIntegration:
    """Proves the snapshot threshold trigger fires at exactly LATTICE_SNAPSHOT_CADENCE events."""

    def test_snapshot_fires_at_cadence_boundary(self, tmp_path: Path) -> None:
        store = FossicStore(tmp_path / "vault")
        store.register_reducer("cerebra/lattice/*", _IdentityReducer())
        emitter = EventEmitter(store, session_id="ses-int", cycle_id="cyc-int")
        lineage = "lin-int-001"
        stream_id = f"cerebra/lattice/{lineage}"

        # Phase 1: fill to CADENCE - 1 events, trigger → no snapshot.
        # Use unique payloads ({"_i": i}) to prevent CCE deduplication.
        for i in range(LATTICE_SNAPSHOT_CADENCE - 1):
            emitter.emit_lattice_event(lineage, "E", {"_i": i})

        assert store.current_version(stream_id) == LATTICE_SNAPSHOT_CADENCE - 1
        emitter.trigger_lattice_snapshots_at_cycle_boundary({lineage})
        assert store.last_snapshot_version(stream_id) == 0  # no snapshot yet

        # Phase 2: add the 100th event, trigger → snapshot fires.
        emitter.emit_lattice_event(lineage, "E", {"_i": LATTICE_SNAPSHOT_CADENCE - 1})
        assert store.current_version(stream_id) == LATTICE_SNAPSHOT_CADENCE
        emitter.trigger_lattice_snapshots_at_cycle_boundary({lineage})
        assert store.last_snapshot_version(stream_id) == LATTICE_SNAPSHOT_CADENCE

        # Phase 3: add CADENCE - 1 more events with non-overlapping indices.
        # Second snapshot should NOT fire yet (delta = CADENCE - 1 < CADENCE).
        for i in range(LATTICE_SNAPSHOT_CADENCE, 2 * LATTICE_SNAPSHOT_CADENCE - 1):
            emitter.emit_lattice_event(lineage, "E", {"_i": i})
        emitter.trigger_lattice_snapshots_at_cycle_boundary({lineage})
        assert store.last_snapshot_version(stream_id) == LATTICE_SNAPSHOT_CADENCE

        # Phase 4: add the 200th event → second snapshot fires.
        emitter.emit_lattice_event(lineage, "E", {"_i": 2 * LATTICE_SNAPSHOT_CADENCE - 1})
        emitter.trigger_lattice_snapshots_at_cycle_boundary({lineage})
        assert store.last_snapshot_version(stream_id) == 2 * LATTICE_SNAPSHOT_CADENCE

    def test_fossic_store_survives_close_and_reopen(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault2"
        store1 = FossicStore(vault)
        store1.register_reducer("cerebra/lattice/*", _IdentityReducer())
        store1.append("cerebra/lattice/persist-test", "E", {"v": 1})
        store1.take_snapshot("cerebra/lattice/persist-test")

        # Reopen — store2 is a fresh instance against the same DB.
        store2 = FossicStore(vault)
        store2.register_reducer("cerebra/lattice/*", _IdentityReducer())
        assert store2.current_version("cerebra/lattice/persist-test") == 1
        assert store2.last_snapshot_version("cerebra/lattice/persist-test") == 1

    def test_causation_chain_round_trip(self, tmp_path: Path) -> None:
        from fossic import ReadQuery

        store = FossicStore(tmp_path / "vault")
        emitter = EventEmitter(store, session_id="ses-caus", cycle_id="cyc-caus")

        e1 = emitter.emit_cycle_event("SessionOpened", {"session": "ses-caus"})
        e2 = emitter.emit_cycle_event("CycleStarted", {"cycle": "cyc-caus"})
        e3 = emitter.emit_cycle_event("StepStarted", {"step": 1})

        events = store._store.read_range(
            ReadQuery(stream_id="cerebra/agent-trace/cyc-caus")
        )
        assert len(events) == 3
        assert events[0].causation_id is None
        assert events[1].causation_id.as_bytes() == e1
        assert events[2].causation_id.as_bytes() == e2
        assert isinstance(e3, bytes)
