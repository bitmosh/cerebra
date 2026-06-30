"""
FossicStore — Cerebra-friendly wrapper around fossic-py v1.

Provides a simplified append/read/snapshot interface on top of fossic's
Store, handling stream auto-declaration, reducer pattern tracking for
snapshot version queries, and Cerebra-specific path conventions.

Store lives at <vault_path>/.fossic/store.db. Multiple CLI invocations
create separate FossicStore instances; fossic's WAL-based SQLite backend
handles concurrent-process safety.

Public API type convention: causation_id is bytes (not EventId) at every
boundary so callers don't need to import fossic types. Conversion to EventId
for Append construction is done internally via EventId.from_hex.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from fossic import (
    Append,
    EventId,
    NoEventsToSnapshotError,
    ReadQuery,
    SnapshotInfo,
    Store,
)


class FossicStore:
    """Cerebra-friendly wrapper around fossic.Store.

    DEV-005 (CCE dedup): Identical events (same event_type + payload +
    causation_id) collapse to the same ID via fossic CCE. Cerebra emission
    paths must ensure causation_id varies for semantically-distinct events.
    """

    def __init__(self, vault_path: Path) -> None:
        db_dir = vault_path / ".fossic"
        db_dir.mkdir(parents=True, exist_ok=True)
        self._store = Store.open(str(db_dir / "store.db"))
        # Maps glob pattern → registered reducer object (for snapshot_info lookups).
        self._reducers: dict[str, Any] = {}

    @classmethod
    def at_platform_path(cls, db_path: Path) -> FossicStore:
        """Open FossicStore at an explicit path (e.g., the platform store).

        Used when Cerebra should write to ~/.lattica/fossic/store.db instead
        of the vault-local store. Creates parent directories if needed.
        """
        instance = cls.__new__(cls)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        instance._store = Store.open(str(db_path))
        instance._reducers = {}
        return instance

    # ── Core write ────────────────────────────────────────────────────────────

    def append(
        self,
        stream_id: str,
        event_type: str,
        payload: dict[str, Any],
        causation_id: bytes | None = None,
        external_id: str | None = None,
        indexed_tags: dict[str, Any] | None = None,
    ) -> bytes:
        """Append an event to a stream, auto-declaring the stream if needed.

        Returns the content-addressed event ID as bytes.
        causation_id is accepted as bytes and converted to EventId internally.
        """
        self._ensure_stream(stream_id)
        causation_eid: EventId | None = (
            EventId.from_hex(causation_id.hex()) if causation_id is not None else None
        )
        eid = self._store.append(
            Append(
                stream_id=stream_id,
                event_type=event_type,
                payload=payload,
                causation_id=causation_eid,
                external_id=external_id,
                indexed_tags=indexed_tags,
            )
        )
        return eid.as_bytes()

    # ── Reducer / aggregate ───────────────────────────────────────────────────

    def register_reducer(self, stream_pattern: str, reducer: Any) -> None:
        """Register a DynReducer against a glob stream pattern.

        The reducer object must implement the fossic reducer protocol:
            name: str
            version: int
            state_schema_version: int
            def initial_state(self) -> Any: ...
            def apply(self, state: Any, event_payload: Any) -> Any: ...
        """
        self._store.register_reducer(stream_pattern, reducer)
        self._reducers[stream_pattern] = reducer

    def read_state(self, stream_id: str, branch: str = "main") -> Any:
        """Return current aggregate state for stream via registered reducer."""
        return self._store.read_state(stream_id, branch)

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def take_snapshot(
        self, stream_id: str, branch: str = "main"
    ) -> SnapshotInfo | None:
        """Persist current aggregate state as a snapshot.

        Returns None if the stream has no events (NoEventsToSnapshotError),
        allowing callers to call unconditionally at cycle boundaries.
        """
        try:
            return self._store.take_snapshot(stream_id, branch)
        except NoEventsToSnapshotError:
            return None

    def current_version(self, stream_id: str, branch: str = "main") -> int:
        """Return the number of events on the stream (0 if stream has no events).

        Defined as len(events), so the first event gives current_version=1.
        This makes cadence checks straightforward: if current_version=100 and
        last_snapshot_version=0, exactly 100 events have accumulated.
        """
        if not self._store.stream_exists(stream_id):
            return 0
        events = self._store.read_range(ReadQuery(stream_id=stream_id, branch=branch))
        return len(events)

    def last_snapshot_version(self, stream_id: str, branch: str = "main") -> int:
        """Return the event count at the time of the last snapshot (0 if none).

        Defined as snapshot.version + 1 to match the current_version convention
        (both count events inclusively). If no snapshot exists, returns 0.
        """
        reducer = self._find_reducer_for_stream(stream_id)
        if reducer is None:
            return 0
        info = self._store.snapshot_info(stream_id, branch, reducer.name)
        if info is None:
            return 0
        # snapshot.version is the 0-based index of the last snapshotted event;
        # +1 converts to the inclusive event count at snapshot time.
        return info.version + 1

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ensure_stream(self, stream_id: str) -> None:
        """Declare the stream if it hasn't been declared yet."""
        if not self._store.stream_exists(stream_id):
            self._store.declare_stream(stream_id, "cerebra", stream_id)

    def read_events(
        self,
        *,
        stream_id: str | None = None,
        stream_pattern: str | None = None,
        event_type: str | None = None,
        branch: str = "main",
        from_version: int | None = None,
    ) -> list[dict[str, Any]]:
        """Read events from a stream or pattern. Returns plain dicts with keys:
        event_type, payload, version, stream_id.

        stream_id reads a single named stream.
        stream_pattern uses glob matching across all streams.
        event_type optionally filters to one event type.
        from_version (stream_id mode only) returns events with version >= that value.
        """
        from fossic import AggregateQuery, ReadQuery

        if stream_id is not None:
            if not self._store.stream_exists(stream_id):
                return []
            kw: dict[str, Any] = {"stream_id": stream_id, "branch": branch}
            if event_type is not None:
                kw["event_type_filter"] = event_type
            if from_version is not None:
                kw["from_version"] = from_version
            events = self._store.read_range(ReadQuery(**kw))
        elif stream_pattern is not None:
            agg_kw: dict[str, Any] = {"stream_pattern": stream_pattern}
            if event_type is not None:
                agg_kw["event_type_filter"] = event_type
            events = self._store.aggregate(AggregateQuery(**agg_kw))
        else:
            raise ValueError("Either stream_id or stream_pattern must be provided.")

        return [
            {
                "event_type": e.event_type,
                "payload": e.payload(),
                "version": getattr(e, "version", 0),
                "stream_id": getattr(e, "stream_id", ""),
            }
            for e in events
        ]

    def _find_reducer_for_stream(self, stream_id: str) -> Any:
        """Find the most-specific registered reducer pattern matching stream_id.

        Returns None if no pattern matches. Specificity: longer (more specific)
        patterns win; among equal-length patterns, fewer wildcards win.
        """
        candidates = []
        for pattern, reducer in self._reducers.items():
            if fnmatch.fnmatch(stream_id, pattern):
                candidates.append((pattern, reducer))
        if not candidates:
            return None
        candidates.sort(key=lambda pr: (-len(pr[0]), pr[0].count("*")))
        return candidates[0][1]
