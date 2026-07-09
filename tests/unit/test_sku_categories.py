# SPDX-License-Identifier: Apache-2.0
"""Unit tests for D1 category table and quadrant logic."""

from __future__ import annotations

import pytest

from cerebra.cognition.sku_categories import (
    CATEGORY_DESCRIPTIONS,
    QUADRANT_NAMES,
    D1Category,
    category_from_name,
    quadrant_of,
)


@pytest.mark.unit
class TestD1Categories:
    def test_exactly_16_categories(self) -> None:
        assert len(D1Category) == 16

    def test_hex_range_0_to_f(self) -> None:
        values = [int(c) for c in D1Category]
        assert sorted(values) == list(range(16))

    def test_all_have_descriptions(self) -> None:
        for cat in D1Category:
            assert cat in CATEGORY_DESCRIPTIONS
            assert len(CATEGORY_DESCRIPTIONS[cat]) > 10

    def test_quadrant_0_is_empirical(self) -> None:
        empirical = [
            D1Category.OBSERVATION,
            D1Category.PATTERN,
            D1Category.MECHANISM,
            D1Category.PHENOMENON,
        ]
        for cat in empirical:
            assert quadrant_of(cat) == 0

    def test_quadrant_1_is_generative(self) -> None:
        generative = [D1Category.TECHNIQUE, D1Category.DESIGN, D1Category.CREATION, D1Category.TOOL]
        for cat in generative:
            assert quadrant_of(cat) == 1

    def test_quadrant_2_is_normative(self) -> None:
        normative = [
            D1Category.PRINCIPLE,
            D1Category.JUDGMENT,
            D1Category.GOAL,
            D1Category.CONSTRAINT,
        ]
        for cat in normative:
            assert quadrant_of(cat) == 2

    def test_quadrant_3_is_relational(self) -> None:
        relational = [D1Category.EVENT, D1Category.AGENT, D1Category.CONTEXT, D1Category.RELATION]
        for cat in relational:
            assert quadrant_of(cat) == 3

    def test_category_from_name_roundtrip(self) -> None:
        for cat in D1Category:
            assert category_from_name(cat.name) == cat

    def test_category_from_name_case_insensitive(self) -> None:
        assert category_from_name("mechanism") == D1Category.MECHANISM
        assert category_from_name("PRINCIPLE") == D1Category.PRINCIPLE

    def test_all_quadrant_names_present(self) -> None:
        assert set(QUADRANT_NAMES.keys()) == {0, 1, 2, 3}

    def test_d1_values_match_spec(self) -> None:
        assert D1Category.OBSERVATION == 0x0
        assert D1Category.MECHANISM == 0x2
        assert D1Category.PRINCIPLE == 0x8
        assert D1Category.RELATION == 0xF
