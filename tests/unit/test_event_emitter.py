# SPDX-License-Identifier: Apache-2.0
"""Unit tests for EventEmitter.

CCE note: fossic deduplicates events with identical content (stream_id, event_type,
payload, causation_id). Tests that append multiple events to the same stream without
varying causation_id must use unique payloads to prevent deduplication.
"""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

import pytest

from cerebra.cognition._constants import LATTICE_SNAPSHOT_CADENCE
from cerebra.cognition.event_emitter import EventEmitter
from cerebra.storage.fossic_store import FossicStore

# Module-level counter for unique payloads.
_SEQ = itertools.count()


def _u(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"_seq": next(_SEQ)}
    if extra:
        payload.update(extra)
    return payload


# ── Minimal reducer for snapshot threshold tests ──────────────────────────────


class _CountReducer:
    name = "count"
    version = 1
    state_schema_version = 1

    def initial_state(self) -> dict[str, int]:
        return {"n": 0}

    def apply(self, state: dict[str, int], _payload: Any) -> dict[str, int]:
        return {"n": state["n"] + 1}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path: Path) -> FossicStore:
    s = FossicStore(tmp_path / "vault")
    s.register_reducer("cerebra/lattice/*", _CountReducer())
    return s


@pytest.fixture
def emitter(store: FossicStore) -> EventEmitter:
    return EventEmitter(store, session_id="ses-001", cycle_id="cyc-001")


# ── emit_cycle_event ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestEmitCycleEvent:
    def test_returns_bytes(self, emitter: EventEmitter) -> None:
        eid = emitter.emit_cycle_event("StepStarted", _u())
        assert isinstance(eid, bytes)
        assert len(eid) == 32

    def test_stream_naming(self, emitter: EventEmitter, store: FossicStore) -> None:
        emitter.emit_cycle_event("StepStarted", _u())
        assert store._store.stream_exists("cerebra/agent-trace/ses-001")
        assert not store._store.stream_exists("cerebra/agent-trace/other")

    def test_first_event_no_causation(self, emitter: EventEmitter, store: FossicStore) -> None:
        from fossic import ReadQuery

        emitter.emit_cycle_event("StepStarted", _u())
        events = store._store.read_range(ReadQuery(stream_id="cerebra/agent-trace/ses-001"))
        assert events[0].causation_id is None

    def test_second_event_auto_chained(self, emitter: EventEmitter, store: FossicStore) -> None:
        from fossic import ReadQuery

        eid1 = emitter.emit_cycle_event("StepStarted", _u())
        emitter.emit_cycle_event("StepExecuted", _u())
        events = store._store.read_range(ReadQuery(stream_id="cerebra/agent-trace/ses-001"))
        assert events[1].causation_id is not None
        assert events[1].causation_id.as_bytes() == eid1

    def test_explicit_causation_overrides_auto(
        self, emitter: EventEmitter, store: FossicStore
    ) -> None:
        from fossic import ReadQuery

        emitter.emit_cycle_event("StepStarted", _u())
        eid_explicit = store.append("other/stream", "E", _u())
        emitter.emit_cycle_event("StepExecuted", _u(), causation_id=eid_explicit)
        events = store._store.read_range(ReadQuery(stream_id="cerebra/agent-trace/ses-001"))
        assert events[1].causation_id.as_bytes() == eid_explicit

    def test_causation_chain_grows_three_events(
        self, emitter: EventEmitter, store: FossicStore
    ) -> None:
        from fossic import ReadQuery

        e1 = emitter.emit_cycle_event("A", _u())
        e2 = emitter.emit_cycle_event("B", _u())
        emitter.emit_cycle_event("C", _u())
        events = store._store.read_range(ReadQuery(stream_id="cerebra/agent-trace/ses-001"))
        assert events[1].causation_id.as_bytes() == e1
        assert events[2].causation_id.as_bytes() == e2

    def test_last_event_id_updated(self, emitter: EventEmitter) -> None:
        assert emitter._last_event_id is None
        e1 = emitter.emit_cycle_event("A", _u())
        assert emitter._last_event_id == e1
        e2 = emitter.emit_cycle_event("B", _u())
        assert emitter._last_event_id == e2

    def test_indexed_tags_forwarded(self, emitter: EventEmitter, store: FossicStore) -> None:
        from fossic import ReadQuery

        emitter.emit_cycle_event("E", _u(), indexed_tags={"k": "v"})
        events = store._store.read_range(ReadQuery(stream_id="cerebra/agent-trace/ses-001"))
        assert events[0].indexed_tags() == {"k": "v"}

    def test_different_sessions_isolated(self, store: FossicStore) -> None:
        # Different sessions go to different streams; same session / different
        # cycles share one stream (cycle_id is a payload field, not a stream segment).
        from fossic import ReadQuery

        e1 = EventEmitter(store, "ses-A", "cyc-1")
        e2 = EventEmitter(store, "ses-B", "cyc-2")
        e1.emit_cycle_event("E", _u({"from": "A"}))
        e2.emit_cycle_event("E", _u({"from": "B"}))
        a_events = store._store.read_range(ReadQuery(stream_id="cerebra/agent-trace/ses-A"))
        b_events = store._store.read_range(ReadQuery(stream_id="cerebra/agent-trace/ses-B"))
        assert len(a_events) == 1
        assert len(b_events) == 1
        assert a_events[0].payload()["from"] == "A"
        assert b_events[0].payload()["from"] == "B"


# ── emit_lattice_event ────────────────────────────────────────────────────────


@pytest.mark.unit
class TestEmitLatticeEvent:
    def test_returns_bytes(self, emitter: EventEmitter) -> None:
        eid = emitter.emit_lattice_event("lineage-1", "LatticeCommit", _u())
        assert isinstance(eid, bytes)

    def test_stream_naming(self, emitter: EventEmitter, store: FossicStore) -> None:
        emitter.emit_lattice_event("lineage-1", "LatticeCommit", _u())
        assert store._store.stream_exists("cerebra/lattice/lineage-1")

    def test_no_auto_causation(self, emitter: EventEmitter, store: FossicStore) -> None:
        from fossic import ReadQuery

        emitter.emit_lattice_event("lin", "E", _u())
        emitter.emit_lattice_event("lin", "E", _u())  # unique payload → 2 events
        events = store._store.read_range(ReadQuery(stream_id="cerebra/lattice/lin"))
        assert len(events) == 2
        # Second lattice event has no auto-causation (unlike cycle events).
        assert events[1].causation_id is None

    def test_explicit_causation_stored(self, emitter: EventEmitter, store: FossicStore) -> None:
        from fossic import ReadQuery

        eid1 = emitter.emit_lattice_event("lin", "E", _u())
        emitter.emit_lattice_event("lin", "E", _u(), causation_id=eid1)
        events = store._store.read_range(ReadQuery(stream_id="cerebra/lattice/lin"))
        assert events[1].causation_id.as_bytes() == eid1

    def test_does_not_pollute_cycle_stream(self, emitter: EventEmitter, store: FossicStore) -> None:
        emitter.emit_lattice_event("lin", "E", _u())
        cycle_stream = "cerebra/agent-trace/ses-001"
        assert not store._store.stream_exists(cycle_stream)

    def test_indexed_tags_forwarded(self, emitter: EventEmitter, store: FossicStore) -> None:
        from fossic import ReadQuery

        emitter.emit_lattice_event("lin", "E", _u(), indexed_tags={"cat": "x"})
        events = store._store.read_range(ReadQuery(stream_id="cerebra/lattice/lin"))
        assert events[0].indexed_tags() == {"cat": "x"}


# ── trigger_lattice_snapshots_at_cycle_boundary ───────────────────────────────


@pytest.mark.unit
class TestTriggerLatticeSnapshots:
    def _fill_stream(
        self,
        emitter: EventEmitter,
        lineage_id: str,
        count: int,
        start: int = 0,
    ) -> None:
        """Append `count` unique events starting at payload index `start`.

        Must use unique payloads to prevent CCE deduplication.
        When calling multiple times for the same stream, pass start=prev_start+prev_count
        to avoid overlapping payload values.
        """
        for i in range(start, start + count):
            emitter.emit_lattice_event(lineage_id, "E", {"_i": i})

    def test_empty_set_no_error(self, emitter: EventEmitter) -> None:
        emitter.trigger_lattice_snapshots_at_cycle_boundary(set())

    def test_below_threshold_no_snapshot(self, emitter: EventEmitter, store: FossicStore) -> None:
        self._fill_stream(emitter, "lin-a", LATTICE_SNAPSHOT_CADENCE - 1)
        emitter.trigger_lattice_snapshots_at_cycle_boundary({"lin-a"})
        # No snapshot → last_snapshot_version stays 0
        assert store.last_snapshot_version("cerebra/lattice/lin-a") == 0

    def test_at_threshold_fires_snapshot(self, emitter: EventEmitter, store: FossicStore) -> None:
        self._fill_stream(emitter, "lin-b", LATTICE_SNAPSHOT_CADENCE)
        emitter.trigger_lattice_snapshots_at_cycle_boundary({"lin-b"})
        lsv = store.last_snapshot_version("cerebra/lattice/lin-b")
        assert lsv == LATTICE_SNAPSHOT_CADENCE

    def test_above_threshold_fires_snapshot(
        self, emitter: EventEmitter, store: FossicStore
    ) -> None:
        self._fill_stream(emitter, "lin-c", LATTICE_SNAPSHOT_CADENCE + 10)
        emitter.trigger_lattice_snapshots_at_cycle_boundary({"lin-c"})
        lsv = store.last_snapshot_version("cerebra/lattice/lin-c")
        assert lsv == LATTICE_SNAPSHOT_CADENCE + 10

    def test_multiple_lineages_independent(self, emitter: EventEmitter, store: FossicStore) -> None:
        # lin-x at threshold, lin-y below threshold
        self._fill_stream(emitter, "lin-x", LATTICE_SNAPSHOT_CADENCE)
        self._fill_stream(emitter, "lin-y", LATTICE_SNAPSHOT_CADENCE - 5)
        emitter.trigger_lattice_snapshots_at_cycle_boundary({"lin-x", "lin-y"})
        assert store.last_snapshot_version("cerebra/lattice/lin-x") == LATTICE_SNAPSHOT_CADENCE
        assert store.last_snapshot_version("cerebra/lattice/lin-y") == 0

    def test_delta_from_last_snapshot(self, emitter: EventEmitter, store: FossicStore) -> None:
        # Fill to CADENCE, snapshot. Then add CADENCE-1 more. Should NOT snapshot again.
        n = LATTICE_SNAPSHOT_CADENCE
        self._fill_stream(emitter, "lin-d", n, start=0)
        emitter.trigger_lattice_snapshots_at_cycle_boundary({"lin-d"})
        # Snapshot taken. Now add CADENCE-1 more with non-overlapping payload indices.
        self._fill_stream(emitter, "lin-d", n - 1, start=n)
        emitter.trigger_lattice_snapshots_at_cycle_boundary({"lin-d"})
        # last_snapshot_version should still be CADENCE (second not triggered)
        assert store.last_snapshot_version("cerebra/lattice/lin-d") == n

    def test_second_cycle_triggers_second_snapshot(
        self, emitter: EventEmitter, store: FossicStore
    ) -> None:
        n = LATTICE_SNAPSHOT_CADENCE
        self._fill_stream(emitter, "lin-e", n, start=0)
        emitter.trigger_lattice_snapshots_at_cycle_boundary({"lin-e"})
        self._fill_stream(emitter, "lin-e", n, start=n)  # non-overlapping indices
        emitter.trigger_lattice_snapshots_at_cycle_boundary({"lin-e"})
        assert store.last_snapshot_version("cerebra/lattice/lin-e") == 2 * n

    def test_untouched_lineages_not_snapshotted(
        self, emitter: EventEmitter, store: FossicStore
    ) -> None:
        self._fill_stream(emitter, "lin-t", LATTICE_SNAPSHOT_CADENCE)
        # Only pass "lin-u", not "lin-t"
        emitter.trigger_lattice_snapshots_at_cycle_boundary({"lin-u"})
        assert store.last_snapshot_version("cerebra/lattice/lin-t") == 0


# ── Session / cycle metadata ──────────────────────────────────────────────────


@pytest.mark.unit
class TestEventEmitterMetadata:
    def test_session_id_accessible(self, emitter: EventEmitter) -> None:
        assert emitter.session_id == "ses-001"

    def test_cycle_id_accessible(self, emitter: EventEmitter) -> None:
        assert emitter.cycle_id == "cyc-001"

    def test_initial_last_event_id_is_none(self, emitter: EventEmitter) -> None:
        assert emitter._last_event_id is None
