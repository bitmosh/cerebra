"""Unit tests for calibration scoring logic."""

from __future__ import annotations

from cerebra.cognition.sku_categories import D1Category
from tests.fixtures.sku_fixtures import SKUFixture


def _score_fixture(predicted: D1Category, fixture: SKUFixture) -> float:
    """Compute partial credit for one prediction."""
    if predicted == fixture.expected_d1:
        return 1.0
    if fixture.ambiguous_with is not None and predicted == fixture.ambiguous_with:
        return 0.5
    return 0.0


def test_exact_match_scores_1():
    fixture = SKUFixture(
        fixture_id="test_01",
        content="test",
        expected_d1=D1Category.PRINCIPLE,
        difficulty="clear",
        ambiguous_with=None,
        notes="",
    )
    assert _score_fixture(D1Category.PRINCIPLE, fixture) == 1.0


def test_ambiguous_match_scores_half():
    fixture = SKUFixture(
        fixture_id="test_02",
        content="test",
        expected_d1=D1Category.TECHNIQUE,
        difficulty="ambiguous",
        ambiguous_with=D1Category.MECHANISM,
        notes="",
    )
    assert _score_fixture(D1Category.MECHANISM, fixture) == 0.5


def test_wrong_prediction_scores_zero():
    fixture = SKUFixture(
        fixture_id="test_03",
        content="test",
        expected_d1=D1Category.PRINCIPLE,
        difficulty="clear",
        ambiguous_with=None,
        notes="",
    )
    assert _score_fixture(D1Category.MECHANISM, fixture) == 0.0


def test_ambiguous_with_none_wrong_scores_zero():
    fixture = SKUFixture(
        fixture_id="test_04",
        content="test",
        expected_d1=D1Category.TECHNIQUE,
        difficulty="ambiguous",
        ambiguous_with=D1Category.MECHANISM,
        notes="",
    )
    assert _score_fixture(D1Category.DESIGN, fixture) == 0.0
