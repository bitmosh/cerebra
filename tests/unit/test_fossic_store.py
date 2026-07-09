# SPDX-License-Identifier: Apache-2.0
"""Unit tests for FossicStore — requires fossic-py (integration-style but fast).

These tests use real fossic stores in tmp_path (no ML models, no full vault init).
They're marked `unit` because they're fast and have no external dependencies,
but they do touch the filesystem via SQLite.

CCE note: fossic deduplicates events with identical (stream_id, event_type, payload,
causation_id, branch). Tests that append multiple events to the same stream must use
unique payloads (e.g. {"_i": i}) to prevent deduplication.
"""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

import pytest

from cerebra.storage.fossic_store import FossicStore

# Module-level counter for unique event payloads (avoids CCE dedup).
_SEQ = itertools.count()


def _u(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a payload that is unique across the entire test session."""
    payload: dict[str, Any] = {"_seq": next(_SEQ)}
    if extra:
        payload.update(extra)
    return payload


# ── Minimal reducers for snapshot tests ───────────────────────────────────────


class CountReducer:
    """Counts events. Used only for snapshot lifecycle tests."""

    name = "count_reducer"
    version = 1
    state_schema_version = 1

    def initial_state(self) -> dict[str, int]:
        return {"count": 0}

    def apply(self, state: dict[str, int], _payload: Any) -> dict[str, int]:
        return {"count": state["count"] + 1}


class TagReducer:
    """Collects event_type strings from payload. For multi-reducer tests."""

    name = "tag_reducer"
    version = 1
    state_schema_version = 1

    def initial_state(self) -> dict[str, list[str]]:
        return {"tags": []}

    def apply(self, state: dict[str, list[str]], payload: Any) -> dict[str, list[str]]:
        tag = payload.get("tag", "?")
        return {"tags": state["tags"] + [tag]}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path: Path) -> FossicStore:
    return FossicStore(tmp_path / "vault")


@pytest.fixture
def store_with_reducer(tmp_path: Path) -> FossicStore:
    s = FossicStore(tmp_path / "vault")
    s.register_reducer("cerebra/lattice/*", CountReducer())
    return s


# ── Initialisation ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestFossicStoreInit:
    def test_creates_fossic_dir(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        FossicStore(vault)
        assert (vault / ".fossic" / "store.db").exists()

    def test_idempotent_double_open(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        FossicStore(vault)
        FossicStore(vault)  # should not raise


# ── Append ────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestFossicStoreAppend:
    def test_returns_bytes(self, store: FossicStore) -> None:
        eid = store.append("s/test", "TestEvent", _u())
        assert isinstance(eid, bytes)
        assert len(eid) == 32  # 256-bit Blake3 hash

    def test_auto_declares_stream(self, store: FossicStore) -> None:
        store.append("s/auto", "TestEvent", _u())
        assert store._store.stream_exists("s/auto")

    def test_auto_declare_idempotent(self, store: FossicStore) -> None:
        store.append("s/auto", "TestEvent", _u())
        store.append("s/auto", "TestEvent", _u())  # should not raise

    def test_roundtrip_payload(self, store: FossicStore) -> None:
        from fossic import ReadQuery

        store.append("s/rt", "Evt", _u({"key": "value", "num": 42}))
        events = store._store.read_range(ReadQuery(stream_id="s/rt"))
        assert len(events) == 1
        payload = events[0].payload()  # payload is a method call
        assert payload["key"] == "value"
        assert payload["num"] == 42

    def test_event_type_stored(self, store: FossicStore) -> None:
        from fossic import ReadQuery

        store.append("s/et", "MyEventType", _u())
        events = store._store.read_range(ReadQuery(stream_id="s/et"))
        assert events[0].event_type == "MyEventType"

    def test_multiple_events_ordered(self, store: FossicStore) -> None:
        from fossic import ReadQuery

        for i in range(3):
            store.append("s/ord", "E", {"i": i, "_seq": next(_SEQ)})
        events = store._store.read_range(ReadQuery(stream_id="s/ord"))
        assert len(events) == 3
        assert [e.payload()["i"] for e in events] == [0, 1, 2]

    def test_streams_isolated(self, store: FossicStore) -> None:
        from fossic import ReadQuery

        store.append("s/a", "E", _u({"from": "a"}))
        store.append("s/b", "E", _u({"from": "b"}))
        a_events = store._store.read_range(ReadQuery(stream_id="s/a"))
        b_events = store._store.read_range(ReadQuery(stream_id="s/b"))
        assert len(a_events) == 1
        assert a_events[0].payload()["from"] == "a"
        assert len(b_events) == 1
        assert b_events[0].payload()["from"] == "b"

    def test_causation_id_stored(self, store: FossicStore) -> None:
        from fossic import ReadQuery

        first = store.append("s/caus", "First", _u())
        store.append("s/caus", "Second", _u(), causation_id=first)
        events = store._store.read_range(ReadQuery(stream_id="s/caus"))
        second = events[1]
        assert second.causation_id is not None
        assert second.causation_id.as_bytes() == first

    def test_causation_id_bytes_round_trip(self, store: FossicStore) -> None:
        eid1 = store.append("s/cr", "E1", _u())
        eid2 = store.append("s/cr", "E2", _u(), causation_id=eid1)
        assert isinstance(eid2, bytes)
        assert eid2 != eid1

    def test_external_id_stored(self, store: FossicStore) -> None:
        from fossic import ReadQuery

        store.append("s/ext", "E", _u(), external_id="ext-abc-123")
        events = store._store.read_range(ReadQuery(stream_id="s/ext"))
        assert events[0].external_id == "ext-abc-123"

    def test_indexed_tags_stored(self, store: FossicStore) -> None:
        from fossic import ReadQuery

        store.append("s/tags", "E", _u(), indexed_tags={"category": "test"})
        events = store._store.read_range(ReadQuery(stream_id="s/tags"))
        assert events[0].indexed_tags() == {"category": "test"}

    def test_no_causation_by_default(self, store: FossicStore) -> None:
        from fossic import ReadQuery

        store.append("s/nc", "E", _u())
        events = store._store.read_range(ReadQuery(stream_id="s/nc"))
        assert events[0].causation_id is None


# ── current_version ───────────────────────────────────────────────────────────


@pytest.mark.unit
class TestCurrentVersion:
    def test_nonexistent_stream_returns_zero(self, store: FossicStore) -> None:
        assert store.current_version("s/never") == 0

    def test_one_event_gives_version_one(self, store: FossicStore) -> None:
        store.append("s/v1", "E", _u())
        assert store.current_version("s/v1") == 1

    def test_increments_per_append(self, store: FossicStore) -> None:
        for i in range(5):
            store.append("s/inc", "E", _u())  # unique payload avoids CCE dedup
            assert store.current_version("s/inc") == i + 1

    def test_independent_streams_independent_versions(self, store: FossicStore) -> None:
        store.append("s/x", "E", _u())
        store.append("s/x", "E", _u())  # unique → 2 events on s/x
        store.append("s/y", "E", _u())
        assert store.current_version("s/x") == 2
        assert store.current_version("s/y") == 1


# ── last_snapshot_version ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestLastSnapshotVersion:
    def test_no_reducer_returns_zero(self, store: FossicStore) -> None:
        store.append("cerebra/lattice/abc", "E", _u())
        assert store.last_snapshot_version("cerebra/lattice/abc") == 0

    def test_no_snapshot_yet_returns_zero(self, store_with_reducer: FossicStore) -> None:
        store_with_reducer.append("cerebra/lattice/abc", "E", _u())
        assert store_with_reducer.last_snapshot_version("cerebra/lattice/abc") == 0

    def test_after_snapshot_returns_event_count(self, store_with_reducer: FossicStore) -> None:
        store_with_reducer.append("cerebra/lattice/abc", "E", _u())
        store_with_reducer.append("cerebra/lattice/abc", "E", _u())  # unique payload
        store_with_reducer.take_snapshot("cerebra/lattice/abc")
        assert store_with_reducer.last_snapshot_version("cerebra/lattice/abc") == 2

    def test_matches_current_version_after_snapshot(self, store_with_reducer: FossicStore) -> None:
        for _ in range(7):
            store_with_reducer.append("cerebra/lattice/xyz", "E", _u())
        store_with_reducer.take_snapshot("cerebra/lattice/xyz")
        cv = store_with_reducer.current_version("cerebra/lattice/xyz")
        lsv = store_with_reducer.last_snapshot_version("cerebra/lattice/xyz")
        assert cv == lsv == 7


# ── take_snapshot ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestTakeSnapshot:
    def test_no_events_returns_none(self, store_with_reducer: FossicStore) -> None:
        store_with_reducer._ensure_stream("cerebra/lattice/empty")
        result = store_with_reducer.take_snapshot("cerebra/lattice/empty")
        assert result is None

    def test_with_events_returns_snapshot_info(self, store_with_reducer: FossicStore) -> None:
        from fossic import SnapshotInfo

        store_with_reducer.append("cerebra/lattice/snap", "E", _u())
        result = store_with_reducer.take_snapshot("cerebra/lattice/snap")
        assert result is not None
        assert isinstance(result, SnapshotInfo)

    def test_snapshot_version_is_0_based_event_index(self, store_with_reducer: FossicStore) -> None:
        for _ in range(3):
            store_with_reducer.append("cerebra/lattice/v3", "E", _u())
        info = store_with_reducer.take_snapshot("cerebra/lattice/v3")
        assert info is not None
        # fossic SnapshotInfo.version is the 0-based index of the last event snapshotted;
        # 3 unique events → versions 0, 1, 2 → snapshot.version == 2.
        assert info.version == 2


# ── register_reducer / read_state ─────────────────────────────────────────────


@pytest.mark.unit
class TestReducerAndReadState:
    def test_reducer_folds_events_correctly(self, store: FossicStore) -> None:
        store.register_reducer("s/fold/*", CountReducer())
        for _ in range(5):
            store.append("s/fold/abc", "E", _u())  # unique payloads avoid CCE dedup
        state = store.read_state("s/fold/abc")
        assert state["count"] == 5

    def test_reducer_pattern_isolation(self, store: FossicStore) -> None:
        store.register_reducer("s/iso/a/*", CountReducer())
        store.append("s/iso/a/1", "E", _u())
        store.append("s/iso/a/1", "E", _u())
        state = store.read_state("s/iso/a/1")
        assert state["count"] == 2


# ── _find_reducer_for_stream (pattern matching) ───────────────────────────────


@pytest.mark.unit
class TestFindReducerForStream:
    def test_no_reducers_returns_none(self, store: FossicStore) -> None:
        assert store._find_reducer_for_stream("cerebra/lattice/abc") is None

    def test_glob_star_matches(self, store: FossicStore) -> None:
        r = CountReducer()
        store._reducers["cerebra/lattice/*"] = r
        assert store._find_reducer_for_stream("cerebra/lattice/abc") is r

    def test_double_star_matches_nested(self, store: FossicStore) -> None:
        r = CountReducer()
        store._reducers["cerebra/**"] = r
        assert store._find_reducer_for_stream("cerebra/lattice/abc") is r

    def test_no_match_returns_none(self, store: FossicStore) -> None:
        store._reducers["other/stream/*"] = CountReducer()
        assert store._find_reducer_for_stream("cerebra/lattice/abc") is None

    def test_specific_pattern_beats_glob(self, store: FossicStore) -> None:
        specific = CountReducer()
        generic = TagReducer()
        store._reducers["cerebra/lattice/abc"] = specific
        store._reducers["cerebra/lattice/*"] = generic
        found = store._find_reducer_for_stream("cerebra/lattice/abc")
        assert found is specific

    def test_longer_glob_beats_shorter_glob(self, store: FossicStore) -> None:
        narrow = CountReducer()
        wide = TagReducer()
        store._reducers["cerebra/lattice/*"] = narrow
        store._reducers["cerebra/**"] = wide
        found = store._find_reducer_for_stream("cerebra/lattice/abc")
        assert found is narrow
