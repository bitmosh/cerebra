"""Integration tests for run_traversal() against the dev vault (745 records).

Skips automatically if numpy is unavailable or the dev vault is absent.
These tests verify that real queries produce sensible candidate sets
(non-empty, correct structure) rather than pinning exact counts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

numpy = pytest.importorskip("numpy", reason="numpy not available — skipping vault traversal tests")

_VAULT = Path.home() / "cerebra-vaults" / "dev" / "data" / "cerebra.db"


@pytest.fixture(scope="module")
def vault_db() -> Path:
    if not _VAULT.exists():
        pytest.skip(f"Dev vault not found at {_VAULT}")
    return _VAULT


@pytest.fixture(scope="module")
def plan_from_vault(vault_db: Path):
    """Return a callable that creates a QueryPlan using the actual vault."""
    from cerebra.retrieval.planner import query_plan
    def _make(query: str, **kwargs):
        return query_plan(query, vault_db, **kwargs)
    return _make


# ── Traversal integration ──────────────────────────────────────────────────────


@pytest.mark.integration
class TestTraversalAgainstVault:
    def test_architecture_query_returns_candidates(self, vault_db: Path, plan_from_vault) -> None:
        from cerebra.retrieval.traversal import run_traversal
        plan = plan_from_vault("retrieval architecture design")
        result = run_traversal(plan, vault_db)
        assert len(result) > 0, "Expected candidates for 'retrieval architecture design'"

    def test_phase_query_returns_candidates(self, vault_db: Path, plan_from_vault) -> None:
        from cerebra.retrieval.traversal import run_traversal
        plan = plan_from_vault("what is the goal of Phase 4")
        result = run_traversal(plan, vault_db)
        assert len(result) > 0, "Expected candidates for goal query"

    def test_identifier_query_lexical_only_mode(self, vault_db: Path, plan_from_vault) -> None:
        from cerebra.retrieval.traversal import run_traversal
        plan = plan_from_vault("drain_pending function")
        assert plan.mode == "lexical_only", f"Expected lexical_only, got {plan.mode}"
        result = run_traversal(plan, vault_db)
        # May return 0 if FTS index not built; that's valid — just check structure
        assert isinstance(result, list)
        for c in result:
            assert c.lexical_score is not None, "lexical_only candidates should have lexical_score"

    def test_leeway_network_query(self, vault_db: Path, plan_from_vault) -> None:
        from cerebra.retrieval.traversal import run_traversal
        plan = plan_from_vault("leeway network")
        result = run_traversal(plan, vault_db)
        assert isinstance(result, list)

    def test_no_duplicate_record_ids(self, vault_db: Path, plan_from_vault) -> None:
        from cerebra.retrieval.traversal import run_traversal
        plan = plan_from_vault("retrieval architecture design")
        result = run_traversal(plan, vault_db)
        ids = [c.record_id for c in result]
        assert len(ids) == len(set(ids)), "Traversal returned duplicate record_ids"

    def test_max_candidates_cap_respected(self, vault_db: Path, plan_from_vault) -> None:
        from cerebra.retrieval.traversal import run_traversal
        plan = plan_from_vault("retrieval architecture design", max_candidates=10)
        result = run_traversal(plan, vault_db)
        assert len(result) <= 10

    def test_retrieval_path_non_empty(self, vault_db: Path, plan_from_vault) -> None:
        from cerebra.retrieval.traversal import run_traversal
        plan = plan_from_vault("retrieval architecture design")
        result = run_traversal(plan, vault_db)
        for c in result:
            assert c.retrieval_path, f"Empty retrieval_path for {c.record_id}"

    def test_sku_match_candidates_have_sku_d1_match(self, vault_db: Path, plan_from_vault) -> None:
        from cerebra.retrieval.traversal import run_traversal
        plan = plan_from_vault("retrieval architecture design")
        result = run_traversal(plan, vault_db)
        # Candidates surfaced via exact_sku or partial_sku must have sku_d1_match=True
        for c in result:
            if c.step_surfaced in ("exact_sku", "partial_sku"):
                assert c.sku_d1_match is True, (
                    f"{c.record_id} surfaced via {c.step_surfaced} but sku_d1_match=False"
                )

    def test_vector_candidates_have_semantic_score(self, vault_db: Path, plan_from_vault) -> None:
        from cerebra.retrieval.traversal import run_traversal
        plan = plan_from_vault("retrieval architecture design")
        result = run_traversal(plan, vault_db)
        for c in result:
            if "vector_fallback" in c.retrieval_path:
                assert c.semantic_score is not None, (
                    f"{c.record_id} has vector_fallback path but semantic_score=None"
                )

    def test_step4_never_adds_candidates_in_v01(self, vault_db: Path, plan_from_vault) -> None:
        from cerebra.retrieval.traversal import run_traversal
        plan = plan_from_vault("the architecture design of the retrieval pipeline")
        result = run_traversal(plan, vault_db)
        # No candidate should be surfaced by sibling_traversal in v0.1
        for c in result:
            assert c.step_surfaced != "sibling_traversal", (
                "Step 4 (sibling_traversal) should not surface candidates in v0.1"
            )
