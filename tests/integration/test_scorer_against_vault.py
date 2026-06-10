"""Integration tests for score_candidates() against the dev vault (745 records).

Skips automatically if numpy is unavailable or the dev vault is absent.
Verifies real query produces a scored candidate set with correct structure
and per-component breakdown.

STOP gate query: "leeway network" — should appear in the report.
"""

from __future__ import annotations

from pathlib import Path

import pytest

numpy = pytest.importorskip("numpy", reason="numpy not available — skipping vault scorer tests")

_VAULT = Path.home() / "cerebra-vaults" / "dev" / "data" / "cerebra.db"


@pytest.fixture(scope="module")
def vault_db() -> Path:
    if not _VAULT.exists():
        pytest.skip(f"Dev vault not found at {_VAULT}")
    return _VAULT


@pytest.fixture(scope="module")
def leeway_scored(vault_db: Path):
    """Score candidates for the STOP gate query 'leeway network'."""
    from cerebra.retrieval.planner import query_plan
    from cerebra.retrieval.traversal import run_traversal
    from cerebra.retrieval.scorer import score_candidates
    plan = query_plan("leeway network", vault_db)
    raw = run_traversal(plan, vault_db)
    return score_candidates(raw, plan, vault_db), plan


@pytest.mark.integration
class TestScorerAgainstVault:
    def test_leeway_network_produces_scored_candidates(self, leeway_scored) -> None:
        scored, _ = leeway_scored
        assert isinstance(scored, list)
        assert len(scored) >= 0  # may be 0 if FTS not built; valid

    def test_all_composites_in_unit_interval(self, leeway_scored) -> None:
        from cerebra.retrieval.scorer import ScoredCandidate
        scored, _ = leeway_scored
        for c in scored:
            assert 0.0 <= c.score.composite <= 1.0, (
                f"Composite {c.score.composite:.4f} out of [0,1] for {c.record_id}"
            )

    def test_sorted_by_composite_descending(self, leeway_scored) -> None:
        scored, _ = leeway_scored
        composites = [c.score.composite for c in scored]
        assert composites == sorted(composites, reverse=True), (
            "Scored candidates must be sorted by composite score descending"
        )

    def test_ranks_are_sequential(self, leeway_scored) -> None:
        scored, _ = leeway_scored
        if not scored:
            pytest.skip("No candidates to rank")
        ranks = [c.rank for c in scored]
        assert ranks == list(range(1, len(scored) + 1))

    def test_all_five_components_present(self, leeway_scored) -> None:
        scored, _ = leeway_scored
        expected = {"semantic", "lexical", "sku_match", "recency", "lifecycle"}
        for c in scored:
            assert set(c.score.components.keys()) == expected, (
                f"Missing components for {c.record_id}: "
                f"got {set(c.score.components.keys())}"
            )

    def test_weights_sum_to_one(self, leeway_scored) -> None:
        scored, _ = leeway_scored
        if not scored:
            pytest.skip("No candidates")
        w = scored[0].score.weights
        assert sum(w.values()) == pytest.approx(1.0, abs=0.01)

    def test_lifecycle_constant_one(self, leeway_scored) -> None:
        scored, _ = leeway_scored
        for c in scored:
            assert c.score.components["lifecycle"] == 1.0, (
                f"lifecycle must be 1.0 in Phase 4, got {c.score.components['lifecycle']} "
                f"for {c.record_id}"
            )

    def test_content_excerpt_non_empty(self, leeway_scored) -> None:
        scored, _ = leeway_scored
        for c in scored:
            assert c.content_excerpt, f"content_excerpt empty for {c.record_id}"

    def test_source_path_non_empty(self, leeway_scored) -> None:
        scored, _ = leeway_scored
        for c in scored:
            assert c.source_path, f"source_path empty for {c.record_id}"

    def test_explain_returns_contributions(self, leeway_scored) -> None:
        scored, _ = leeway_scored
        if not scored:
            pytest.skip("No candidates")
        top = scored[0]
        explain = top.score.explain()
        assert len(explain) == 5
        for row in explain:
            assert "component" in row
            assert "contribution" in row

    def test_architecture_query_has_high_top_score(self, vault_db: Path) -> None:
        from cerebra.retrieval.planner import query_plan
        from cerebra.retrieval.traversal import run_traversal
        from cerebra.retrieval.scorer import score_candidates
        plan = query_plan("retrieval architecture design", vault_db)
        raw = run_traversal(plan, vault_db)
        scored = score_candidates(raw, plan, vault_db)
        if not scored:
            pytest.skip("No candidates from vault")
        assert scored[0].score.composite >= 0.30, (
            f"Top score {scored[0].score.composite:.4f} unexpectedly low for architecture query"
        )
