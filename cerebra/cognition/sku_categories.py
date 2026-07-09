# SPDX-License-Identifier: Apache-2.0
"""
D1 cognitive categories — the 16 primary classification targets.

Categories are organized in four quadrants of four, encoded as a single
hex nibble (0x0–0xF). The quadrant is readable from the high 2 bits
(0x0–0x3=Empirical, 0x4–0x7=Generative, 0x8–0xB=Normative, 0xC–0xF=Relational).

These are cognitive shapes, not content topics. The same taxonomy applies
across every domain because shapes of thinking are stable across centuries
and cultures.
"""

from __future__ import annotations

from enum import IntEnum


class D1Category(IntEnum):
    # Quadrant I — Empirical / Sense-Making (how things are)
    OBSERVATION = 0x0
    PATTERN = 0x1
    MECHANISM = 0x2
    PHENOMENON = 0x3
    # Quadrant II — Generative / Making (how things come to be)
    TECHNIQUE = 0x4
    DESIGN = 0x5
    CREATION = 0x6
    TOOL = 0x7
    # Quadrant III — Normative / Valuing (how things should be)
    PRINCIPLE = 0x8
    JUDGMENT = 0x9
    GOAL = 0xA
    CONSTRAINT = 0xB
    # Quadrant IV — Relational / Connecting (how things relate)
    EVENT = 0xC
    AGENT = 0xD
    CONTEXT = 0xE
    RELATION = 0xF


# Quadrant mask: high 2 bits determine quadrant (0=Empirical, 1=Generative,
# 2=Normative, 3=Relational). Applied as (d1 >> 2) & 0x3.
QUADRANT_NAMES: dict[int, str] = {
    0: "Empirical",
    1: "Generative",
    2: "Normative",
    3: "Relational",
}


# Descriptions used verbatim in the classification prompt.
# One line each: what the category means, not examples of it.
CATEGORY_DESCRIPTIONS: dict[D1Category, str] = {
    D1Category.OBSERVATION: "direct data, raw events, measurements, sensor records, logged occurrences",
    D1Category.PATTERN: "recurrence, regularity, structure detected across multiple observations",
    D1Category.MECHANISM: "how something works; causal chains; process understanding; operational logic",
    D1Category.PHENOMENON: "named things, bounded entities, 'what it is' knowledge; definitions",
    D1Category.TECHNIQUE: "procedural how-to; methods; craft; step-by-step instructions; recipes",
    D1Category.DESIGN: "intentional structure; choices made for purposes; architecture; schema",
    D1Category.CREATION: "artifacts produced; outputs; works; expressions; things that were made",
    D1Category.TOOL: "instruments and capabilities used to make or do things; systems as enablers",
    D1Category.PRINCIPLE: "rules, doctrines, ethics; normative 'should' statements; doctrine",
    D1Category.JUDGMENT: "evaluations, critiques, appraisals; weighing tradeoffs; assessments",
    D1Category.GOAL: "desired states; intentions; what is being pursued; targets",
    D1Category.CONSTRAINT: "limits, prohibitions, what must not happen; hard boundaries",
    D1Category.EVENT: "things that happened at a specific time; situated moments; history",
    D1Category.AGENT: "persons, organizations, systems with intent; actors; stakeholders",
    D1Category.CONTEXT: "settings, environments, scopes, backgrounds; the container of action",
    D1Category.RELATION: "connections between things; dependencies, influences, references",
}


def quadrant_of(category: D1Category) -> int:
    """Return the quadrant index (0–3) for a category."""
    return (int(category) >> 2) & 0x3


def category_from_name(name: str) -> D1Category:
    """Look up a D1Category by its uppercase name string."""
    return D1Category[name.upper()]
