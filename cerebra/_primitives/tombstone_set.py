"""
A set with three states per item: present, tombstoned, absent.

Tombstoned items don't return on retrieval but block re-insertion of
identical items unless explicit restore.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ItemState(Enum):
    PRESENT = "present"
    TOMBSTONED = "tombstoned"
    ABSENT = "absent"


@dataclass
class TombstoneInfo:
    reason: str
    tombstoned_at: int  # unix timestamp
    tombstoned_by: str  # actor


class TombstoneSet:
    def __init__(self) -> None:
        self._present: dict[str, Any] = {}
        self._tombstoned: dict[str, TombstoneInfo] = {}

    def add(self, item_id: str, value: Any) -> bool:
        """Add item. Returns True if added, False if blocked by tombstone."""
        if item_id in self._tombstoned:
            return False
        self._present[item_id] = value
        return True

    def tombstone(self, item_id: str, reason: str, timestamp: int, actor: str) -> None:
        """Tombstone an item. Removes from present, marks tombstoned."""
        if item_id in self._present:
            del self._present[item_id]
        self._tombstoned[item_id] = TombstoneInfo(
            reason=reason,
            tombstoned_at=timestamp,
            tombstoned_by=actor,
        )

    def restore(self, item_id: str, value: Any) -> None:
        """Explicitly restore a tombstoned item."""
        if item_id in self._tombstoned:
            del self._tombstoned[item_id]
        self._present[item_id] = value

    def state(self, item_id: str) -> ItemState:
        if item_id in self._present:
            return ItemState.PRESENT
        if item_id in self._tombstoned:
            return ItemState.TOMBSTONED
        return ItemState.ABSENT

    def get(self, item_id: str) -> Any | None:
        """Get item if present. Returns None for tombstoned or absent."""
        return self._present.get(item_id)

    def get_with_tombstones(
        self, item_id: str
    ) -> tuple[Any | None, ItemState, TombstoneInfo | None]:
        """Get (value, state, tombstone_info). For audit/admin contexts."""
        if item_id in self._present:
            return (self._present[item_id], ItemState.PRESENT, None)
        if item_id in self._tombstoned:
            return (None, ItemState.TOMBSTONED, self._tombstoned[item_id])
        return (None, ItemState.ABSENT, None)

    def __contains__(self, item_id: object) -> bool:
        return item_id in self._present

    def __len__(self) -> int:
        return len(self._present)
