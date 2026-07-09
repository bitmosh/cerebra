# SPDX-License-Identifier: Apache-2.0
"""
SKU address model — data structures for SKU addresses and assignments.

Address format: D1D2D3D4D5D6.D7D8.D9D10  (12-char string with two dots)
  Location (D1-D6): 6 single hex chars — cognitive position
  Entry   (D7-D8): 2 hex chars as one byte — per-location occupancy index
  Tag     (D9-D10): 2 single hex chars — modality + provenance

Each Di is a single hex nibble (0x0–0xF). D7-D8 together form a byte
(0x00–0xFF), representing up to 256 entries per location address.

Phase 2 stubs: D2=D3=D4=D5=D6=0x0 with subcategory_strategy_version='v1-stub'.
D10 is always 0x0 (observed) for ingested content.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class D9Modality(IntEnum):
    TEXT = 0x0
    CODE = 0x1
    GRAPH = 0x2
    CONVERSATION = 0x3
    OBSERVATION = 0x4
    DECISION = 0x5
    SYNTHESIS = 0x6
    UNKNOWN = 0x7


class D10Provenance(IntEnum):
    OBSERVED = 0x0
    CONSOLIDATED = 0x1
    SYNTHESIZED = 0x2
    USER_PIN = 0x3
    EXTERNAL = 0x4
    SYSTEM = 0x5
    UNKNOWN = 0x6


def d9_from_detected_type(detected_type: str) -> D9Modality:
    """Heuristic D9 assignment from source detected_type. No LLM needed."""
    mapping = {
        "markdown": D9Modality.TEXT,
        "text": D9Modality.TEXT,
        "code": D9Modality.CODE,
        "graph": D9Modality.GRAPH,
    }
    return mapping.get(detected_type.lower(), D9Modality.UNKNOWN)


@dataclass
class SKUAddress:
    """10-digit hex SKU address organized as 6+2+2."""

    d1: int  # 0x0–0xF primary cognitive category
    d2: int = 0  # 0x0 stub (subcategory_strategy_version='v1-stub')
    d3: int = 0  # 0x0 stub
    d4: int = 0  # 0x0 null (inapplicable while D2/D3 stubbed)
    d5: int = 0  # 0x0 deferred to v0.2 (temporal band)
    d6: int = 0  # 0x0 deferred to v0.2 (novelty band)
    d7: int = 0  # high nibble of entry index byte
    d8: int = 0  # low nibble of entry index byte
    d9: int = 0  # D9Modality
    d10: int = 0  # D10Provenance

    def __post_init__(self) -> None:
        for name, val in (
            ("d1", self.d1),
            ("d2", self.d2),
            ("d3", self.d3),
            ("d4", self.d4),
            ("d5", self.d5),
            ("d6", self.d6),
            ("d7", self.d7),
            ("d8", self.d8),
            ("d9", self.d9),
            ("d10", self.d10),
        ):
            if not (0 <= val <= 0xF):
                raise ValueError(f"SKU digit {name} out of range: {val!r}")

    @property
    def entry_index(self) -> int:
        """Entry index as a byte (0–255): high nibble D7, low nibble D8."""
        return (self.d7 << 4) | self.d8

    def to_hex_string(self) -> str:
        """Render as 'D1D2D3D4D5D6.D7D8.D9D10'."""
        loc = f"{self.d1:X}{self.d2:X}{self.d3:X}{self.d4:X}{self.d5:X}{self.d6:X}"
        entry = f"{self.entry_index:02X}"
        tag = f"{self.d9:X}{self.d10:X}"
        return f"{loc}.{entry}.{tag}"

    @classmethod
    def from_hex_string(cls, s: str) -> SKUAddress:
        """Parse 'D1D2D3D4D5D6.D7D8.D9D10' back to SKUAddress."""
        parts = s.split(".")
        if len(parts) != 3 or len(parts[0]) != 6 or len(parts[1]) != 2 or len(parts[2]) != 2:
            raise ValueError(f"Invalid SKU address format: {s!r}")
        loc, entry_hex, tag = parts
        entry_byte = int(entry_hex, 16)
        return cls(
            d1=int(loc[0], 16),
            d2=int(loc[1], 16),
            d3=int(loc[2], 16),
            d4=int(loc[3], 16),
            d5=int(loc[4], 16),
            d6=int(loc[5], 16),
            d7=(entry_byte >> 4) & 0xF,
            d8=entry_byte & 0xF,
            d9=int(tag[0], 16),
            d10=int(tag[1], 16),
        )

    def as_location_tuple(self) -> tuple[int, int, int, int, int, int, int, int]:
        """Return full location tuple for occupancy count queries."""
        return (self.d1, self.d2, self.d3, self.d4, self.d5, self.d6, self.d9, self.d10)


@dataclass
class SKUAssignment:
    """Full classifier output for one memory record's SKU assignment."""

    assignment_id: str
    record_id: str
    sku_address: SKUAddress
    raw_scores: dict[str, float]  # all 16 D1 category scores
    d1_confidence: float
    classifier_version: str
    prompt_version: str
    subcategory_strategy_version: str
    model_string: str | None
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    created_at: int
    pass_count: int = 1
    raw_scores_json_override: str | None = (
        None  # two-pass combined JSON; if set, used instead of raw_scores
    )

    @property
    def sku_address_str(self) -> str:
        return self.sku_address.to_hex_string()

    def as_dict(self) -> dict[str, object]:
        import json

        addr = self.sku_address
        return {
            "assignment_id": self.assignment_id,
            "record_id": self.record_id,
            "sku_address": self.sku_address_str,
            "d1": addr.d1,
            "d2": addr.d2,
            "d3": addr.d3,
            "d4": addr.d4,
            "d5": addr.d5,
            "d6": addr.d6,
            "d7": addr.d7,
            "d8": addr.d8,
            "d9": addr.d9,
            "d10": addr.d10,
            "raw_scores_json": (
                self.raw_scores_json_override
                if self.raw_scores_json_override is not None
                else json.dumps(self.raw_scores)
            ),
            "d1_confidence": self.d1_confidence,
            "classifier_version": self.classifier_version,
            "prompt_version": self.prompt_version,
            "subcategory_strategy_version": self.subcategory_strategy_version,
            "model_string": self.model_string,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "pass_count": self.pass_count,
            "created_at": self.created_at,
            "schema_version": 1,
        }
