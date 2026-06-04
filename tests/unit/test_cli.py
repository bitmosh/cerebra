"""Unit tests for the CLI entry point."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from cerebra.cli.main import cli


@pytest.mark.unit
class TestCLI:
    def test_version(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.0.0" in result.output

    def test_init_creates_vault(self, tmp_path: Path) -> None:
        runner = CliRunner()
        target = str(tmp_path / "new-vault")
        result = runner.invoke(cli, ["init", target])
        assert result.exit_code == 0
        assert "Vault initialized" in result.output
        assert (tmp_path / "new-vault" / "config.yaml").exists()

    def test_init_fails_on_double_init(self, tmp_path: Path) -> None:
        runner = CliRunner()
        target = str(tmp_path / "vault")
        runner.invoke(cli, ["init", target])
        result = runner.invoke(cli, ["init", target])
        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_init_force_reinits(self, tmp_path: Path) -> None:
        runner = CliRunner()
        target = str(tmp_path / "vault")
        runner.invoke(cli, ["init", target])
        result = runner.invoke(cli, ["init", "--force", target])
        assert result.exit_code == 0
