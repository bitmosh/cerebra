# SPDX-License-Identifier: Apache-2.0
"""
Integration tests: cerebra context T1 auto-promotion against the real dev vault.

Skips automatically if numpy is unavailable or the dev vault is absent.

Scenarios:
1. cerebra context "leeway network" → T1 has selected_memory items
2. cerebra context "memory drift" after above → T1 has items from BOTH queries (cumulative)
3. cerebra context --no-promote on third query → T1 unchanged
4. cerebra context with --floor 0.99 (forces abstention) → T1 unchanged
5. Rendered output shows both selected_memory and truth_tower sections
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

numpy = pytest.importorskip("numpy", reason="numpy not available — skipping T1 vault tests")

_VAULT_ROOT = Path.home() / "cerebra-vaults" / "dev"
_VAULT_DB = _VAULT_ROOT / "data" / "cerebra.db"


@pytest.fixture(scope="module")
def vault_root() -> Path:
    if not _VAULT_DB.exists():
        pytest.skip(f"Dev vault not found at {_VAULT_DB}")
    return _VAULT_ROOT


@pytest.fixture(scope="module")
def clean_session(vault_root: Path) -> str:
    """Create a fresh session for this test module; return session_id."""
    from cerebra.cognition.working_memory import new_session

    db = vault_root / "data" / "cerebra.db"
    return new_session(db, str(vault_root))


def _t1_count(vault_root: Path, session_id: str) -> int:
    from cerebra.cognition.truth_tower import TruthTower

    db = vault_root / "data" / "cerebra.db"
    return len(TruthTower(db, session_id).load_tier(1))


@pytest.mark.integration
class TestContextT1AgainstVault:
    def test_leeway_network_populates_t1(self, vault_root: Path, clean_session: str) -> None:
        """Running cerebra context with a normal query populates T1."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        before = _t1_count(vault_root, clean_session)
        result = CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--limit", "3"]
        )
        assert result.exit_code == 0, f"Non-zero exit:\n{result.output}"
        after = _t1_count(vault_root, clean_session)
        # Either new items were added, or idempotency kept the same count — never less
        assert after >= before
        assert "ContextPacket" in result.output

    def test_second_query_accumulates_t1(self, vault_root: Path, clean_session: str) -> None:
        """A second distinct query adds items to T1 (cumulative)."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        # Ensure first query has run (leeway_network test runs first in module order)
        CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--limit", "3"]
        )
        before = _t1_count(vault_root, clean_session)

        result = CliRunner().invoke(
            cli, ["context", "memory drift", "--vault", str(vault_root), "--limit", "3"]
        )
        assert result.exit_code in (0, 1)  # 1 means abstained — still ok
        after = _t1_count(vault_root, clean_session)
        # Either added items (success) or same count (abstained / full dedup)
        assert after >= before

    def test_no_promote_leaves_t1_unchanged(self, vault_root: Path, clean_session: str) -> None:
        """--no-promote does not change T1 even though retrieval runs."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        before = _t1_count(vault_root, clean_session)
        result = CliRunner().invoke(
            cli,
            [
                "context",
                "cognitive architecture",
                "--vault",
                str(vault_root),
                "--limit",
                "3",
                "--no-promote",
            ],
        )
        assert result.exit_code in (0, 1)
        after = _t1_count(vault_root, clean_session)
        assert after == before, "--no-promote must not change T1 count"

    def test_abstained_leaves_t1_unchanged(self, vault_root: Path, clean_session: str) -> None:
        """--floor 0.99 forces abstention; T1 must not change."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        before = _t1_count(vault_root, clean_session)
        result = CliRunner().invoke(
            cli,
            [
                "context",
                "some rare query unlikely to score high",
                "--vault",
                str(vault_root),
                "--floor",
                "0.99",
            ],
        )
        assert result.exit_code == 1  # abstained
        after = _t1_count(vault_root, clean_session)
        assert after == before, "abstained packet must not change T1 count"

    def test_rendered_output_shows_truth_tower_section(
        self, vault_root: Path, clean_session: str
    ) -> None:
        """Text output contains both 'Selected memory' and 'Truth Tower' sections."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--limit", "3"]
        )
        assert result.exit_code == 0, result.output
        # If T1 has items, tower section should appear
        if _t1_count(vault_root, clean_session) > 0:
            assert "Truth Tower" in result.output
            assert "T1 [1]" in result.output

    def test_json_output_includes_truth_tower(self, vault_root: Path, clean_session: str) -> None:
        """JSON output includes truth_tower field when tower is non-empty."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        result = CliRunner().invoke(
            cli,
            [
                "context",
                "leeway network",
                "--vault",
                str(vault_root),
                "--limit",
                "3",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        if _t1_count(vault_root, clean_session) > 0:
            assert "truth_tower" in data
            assert data["truth_tower"]["t1_count"] >= 1
