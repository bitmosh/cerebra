"""
D4 relationship axis — the 16 types encoding how D2 relates to D3.

Organized in four families of four. The constrained vocabulary is what
makes D4 useful: "given D2 and D3, which of these 16 relationships best
describes how they connect?" is tractable in a way that open-ended
relationship labeling is not.

Phase 2: D4 = 0x0 (inapplicable) because D2/D3 are stubbed. D4
classification activates when CEREBRA_SKU_SUBCATEGORIES.md lands.
"""

from __future__ import annotations

from enum import IntEnum


class D4Relationship(IntEnum):
    # Comparative family
    ANALOGY = 0x0  # D2 is structurally similar to D3
    CONTRAST = 0x1  # D2 differs sharply from D3 in instructive ways
    UNIFICATION = 0x2  # D2 and D3 are revealed as the same underlying thing
    TENSION = 0x3  # D2 and D3 are in productive conflict
    # Causal family
    ENABLES = 0x4  # D2 makes D3 possible or easier
    PREVENTS = 0x5  # D2 blocks or constrains D3
    EMERGES_FROM = 0x6  # D3 arises as a consequence of D2
    TRANSFORMS = 0x7  # D2 changes D3 in a specific way
    # Compositional family
    CONTAINS = 0x8  # D2 has D3 as part of itself
    PART_OF = 0x9  # D2 is a piece of D3
    COMPOSES = 0xA  # D2 and D3 together form a larger whole
    DECOMPOSES = 0xB  # D2 breaks down into D3 (among others)
    # Operational family
    APPLIES_TO = 0xC  # D2 is used on or against D3
    CRITIQUES = 0xD  # D2 evaluates or challenges D3
    SERVES = 0xE  # D2 exists in service of D3
    DERIVES_FROM = 0xF  # D2 is calculated, learned, or extracted from D3


# D4_NULL is the Phase 2 placeholder — inapplicable when D2/D3 are stubbed.
D4_NULL = D4Relationship.ANALOGY  # 0x0; semantically "unspecified" at strategy v1
