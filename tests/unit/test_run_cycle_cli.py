# SPDX-License-Identifier: Apache-2.0
"""Phase 8 Step 3 unit tests — cerebra run-cycle CLI command.

Run with: pytest tests/unit/test_run_cycle_cli.py -v
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from cerebra.cli.main import cli
from cerebra.cognition.llm_adapter import ClassificationResult, LLMAdapter
from cerebra.storage.migrations import run_migrations

# ── Stub LLM ─────────────────────────────────────────────────────────────────


class _StubLLM(LLMAdapter):
    def __init__(self, text: str = "cli stub output", score: float = 0.80) -> None:
        self._text = text
        self._score = score

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        return self._text

    def complete_structured(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "checks": [{"item": i, "severity": 0, "specific_lines": ""} for i in range(1, 6)],
            "overall_score": self._score,
            "reasoning": "cli stub",
        }

    def classify_d1(self, content: str) -> ClassificationResult:
        raise NotImplementedError

    def classify_quadrant(self, content: str) -> ClassificationResult:
        raise NotImplementedError

    def classify_within_quadrant(self, content: str, quadrant: str) -> ClassificationResult:
        raise NotImplementedError

    def health_check(self) -> bool:
        return True


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    db_path = tmp_path / "data" / "cerebra.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    run_migrations(db_path)
    return tmp_path


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _invoke(runner: CliRunner, vault: Path, args: list[str]) -> Any:
    """Invoke run-cycle with OllamaDirectAdapter patched to _StubLLM."""
    with patch(
        "cerebra.cognition.llm_adapter.OllamaDirectAdapter",
        return_value=_StubLLM(),
    ):
        return runner.invoke(
            cli,
            ["run-cycle", "--vault", str(vault)] + args,
            catch_exceptions=False,
        )


# ── Happy path ────────────────────────────────────────────────────────────────


class TestRunCycleCLIHappyPath:
    def test_exit_0_on_accept(self, runner: CliRunner, vault: Path) -> None:
        result = _invoke(
            runner,
            vault,
            ["simple.planning.v0", "--goal", "design a search feature"],
        )
        assert result.exit_code == 0, result.output

    def test_prints_session_id(self, runner: CliRunner, vault: Path) -> None:
        result = _invoke(
            runner,
            vault,
            ["simple.planning.v0", "--goal", "design a feature"],
        )
        assert "Session:" in result.output

    def test_prints_cycle_id(self, runner: CliRunner, vault: Path) -> None:
        result = _invoke(
            runner,
            vault,
            ["simple.planning.v0", "--goal", "design a feature"],
        )
        assert "Cycle:" in result.output

    def test_prints_outcome(self, runner: CliRunner, vault: Path) -> None:
        result = _invoke(
            runner,
            vault,
            ["simple.planning.v0", "--goal", "design a feature"],
        )
        assert "Outcome:" in result.output

    def test_quiet_suppresses_progress(self, runner: CliRunner, vault: Path) -> None:
        result = _invoke(
            runner,
            vault,
            ["simple.planning.v0", "--goal", "design a feature", "--quiet"],
        )
        assert result.exit_code == 0, result.output
        assert "Session:" not in result.output
        assert "Cycle:" not in result.output

    def test_verbose_prints_step_detail(self, runner: CliRunner, vault: Path) -> None:
        result = _invoke(
            runner,
            vault,
            ["simple.planning.v0", "--goal", "design a feature", "--verbose"],
        )
        assert result.exit_code == 0, result.output
        assert "step " in result.output.lower()

    def test_max_steps_override(self, runner: CliRunner, vault: Path) -> None:
        result = _invoke(
            runner,
            vault,
            ["simple.planning.v0", "--goal", "design a feature", "--max-steps", "1"],
        )
        assert result.exit_code in (0, 1), result.output

    def test_continue_stub_prints_note(self, runner: CliRunner, vault: Path) -> None:
        result = _invoke(
            runner,
            vault,
            ["simple.planning.v0", "--goal", "design a feature", "--continue", "sess_abc"],
        )
        assert "stub" in result.output.lower()


# ── Dry-run ───────────────────────────────────────────────────────────────────


class TestRunCycleDryRun:
    def test_dry_run_exit_0(self, runner: CliRunner, vault: Path) -> None:
        result = _invoke(
            runner,
            vault,
            ["simple.planning.v0", "--goal", "design a feature", "--dry-run"],
        )
        assert result.exit_code == 0, result.output

    def test_dry_run_prints_config_name(self, runner: CliRunner, vault: Path) -> None:
        result = _invoke(
            runner,
            vault,
            ["simple.planning.v0", "--goal", "my goal", "--dry-run"],
        )
        assert "simple.planning.v0" in result.output

    def test_dry_run_prints_goal(self, runner: CliRunner, vault: Path) -> None:
        result = _invoke(
            runner,
            vault,
            ["simple.planning.v0", "--goal", "my goal", "--dry-run"],
        )
        assert "my goal" in result.output

    def test_dry_run_no_cycle_executed(self, runner: CliRunner, vault: Path) -> None:
        result = _invoke(
            runner,
            vault,
            ["simple.planning.v0", "--goal", "design a feature", "--dry-run"],
        )
        assert "no cycle executed" in result.output.lower()


# ── Error paths ───────────────────────────────────────────────────────────────


class TestRunCycleCLIErrors:
    def test_missing_goal_fails(self, runner: CliRunner, vault: Path) -> None:
        result = runner.invoke(
            cli,
            ["--vault", str(vault), "run-cycle", "simple.planning.v0"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0

    def test_unknown_config_exits_2(self, runner: CliRunner, vault: Path) -> None:
        with patch("cerebra.cognition.llm_adapter.OllamaDirectAdapter", return_value=_StubLLM()):
            result = runner.invoke(
                cli,
                ["run-cycle", "--vault", str(vault), "nonexistent.config.v0", "--goal", "goal"],
                catch_exceptions=False,
            )
        assert result.exit_code == 2, result.output

    def test_missing_vault_exits_2(self, runner: CliRunner, tmp_path: Path) -> None:
        bad_vault = tmp_path / "no_such_vault"
        with patch("cerebra.cognition.llm_adapter.OllamaDirectAdapter", return_value=_StubLLM()):
            result = runner.invoke(
                cli,
                ["run-cycle", "--vault", str(bad_vault), "simple.planning.v0", "--goal", "goal"],
                catch_exceptions=False,
            )
        assert result.exit_code == 2, result.output
