"""Unit tests for the `cerebra reindex` CLI command."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from cerebra.cli.main import cli

# ── Helpers ───────────────────────────────────────────────────────────────────


def _patched_lexical(record_count: int = 10, indexed_count: int = 10):
    """Context manager that patches the lexical reindex pipeline."""
    import contextlib
    from pathlib import Path

    @contextlib.contextmanager
    def _cm():
        with (
            patch("cerebra.cli.main._get_vault", return_value=Path("/fake/vault")),
            patch("cerebra.storage.migrations.run_migrations"),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "cerebra.storage.db.connect",
            ) as mock_connect,
            patch(
                "cerebra.storage.lexical.build_fts_index",
                return_value=indexed_count,
            ),
        ):
            mock_conn = mock_connect.return_value.__enter__.return_value
            mock_conn.execute.return_value.fetchone.return_value = [record_count]
            yield

    return _cm()


# ── No-args behaviour ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestReindexNoArgs:
    def test_no_args_exits_zero(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["reindex"])
        assert result.exit_code == 0, result.output

    def test_no_args_prints_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["reindex"])
        assert "--lexical" in result.output
        assert "--vector" in result.output

    def test_help_flag_exits_zero(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["reindex", "--help"])
        assert result.exit_code == 0

    def test_help_flag_mentions_fts5(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["reindex", "--help"])
        assert "FTS5" in result.output or "lexical" in result.output


# ── --lexical flag ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestReindexLexical:
    def test_lexical_exits_zero(self) -> None:
        runner = CliRunner()
        with _patched_lexical():
            result = runner.invoke(cli, ["reindex", "--lexical"])
        assert result.exit_code == 0, result.output

    def test_lexical_prints_record_count(self) -> None:
        runner = CliRunner()
        with _patched_lexical(record_count=745):
            result = runner.invoke(cli, ["reindex", "--lexical"])
        assert "745" in result.output

    def test_lexical_prints_indexed_count(self) -> None:
        runner = CliRunner()
        with _patched_lexical(record_count=745, indexed_count=745):
            result = runner.invoke(cli, ["reindex", "--lexical"])
        assert "745 records indexed" in result.output

    def test_lexical_prints_done(self) -> None:
        runner = CliRunner()
        with _patched_lexical():
            result = runner.invoke(cli, ["reindex", "--lexical"])
        assert "Done" in result.output

    def test_lexical_calls_build_fts_index(self) -> None:
        runner = CliRunner()
        with (
            _patched_lexical() as _,
            patch("cerebra.storage.lexical.build_fts_index", return_value=10) as mock_build,
            patch(
                "cerebra.cli.main._get_vault",
                return_value=__import__("pathlib").Path("/fake/vault"),
            ),
            patch("cerebra.storage.migrations.run_migrations"),
            patch("pathlib.Path.exists", return_value=True),
            patch("cerebra.storage.db.connect") as mc,
        ):
            mc.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = [10]
            result = runner.invoke(cli, ["reindex", "--lexical"])
        assert result.exit_code == 0
        mock_build.assert_called_once()

    def test_lexical_vault_not_found_exits_two(self) -> None:
        runner = CliRunner()
        with (
            patch(
                "cerebra.cli.main._get_vault",
                return_value=__import__("pathlib").Path("/fake/vault"),
            ),
            patch("pathlib.Path.exists", return_value=False),
        ):
            result = runner.invoke(cli, ["reindex", "--lexical"])
        assert result.exit_code == 2

    def test_lexical_build_error_exits_two(self) -> None:
        runner = CliRunner()
        with (
            patch(
                "cerebra.cli.main._get_vault",
                return_value=__import__("pathlib").Path("/fake/vault"),
            ),
            patch("cerebra.storage.migrations.run_migrations"),
            patch("pathlib.Path.exists", return_value=True),
            patch("cerebra.storage.db.connect") as mc,
            patch(
                "cerebra.storage.lexical.build_fts_index",
                side_effect=RuntimeError("fts explosion"),
            ),
        ):
            mc.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = [5]
            result = runner.invoke(cli, ["reindex", "--lexical"])
        assert result.exit_code == 2

    def test_lexical_error_message_on_stderr(self) -> None:
        runner = CliRunner()
        with (
            patch(
                "cerebra.cli.main._get_vault",
                return_value=__import__("pathlib").Path("/fake/vault"),
            ),
            patch("cerebra.storage.migrations.run_migrations"),
            patch("pathlib.Path.exists", return_value=True),
            patch("cerebra.storage.db.connect") as mc,
            patch(
                "cerebra.storage.lexical.build_fts_index",
                side_effect=RuntimeError("fts explosion"),
            ),
        ):
            mc.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = [5]
            result = runner.invoke(cli, ["reindex", "--lexical"])
        assert "lexical reindex failed" in result.output


# ── --vector flag ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestReindexVector:
    def test_vector_alone_exits_two(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["reindex", "--vector"])
        assert result.exit_code == 2

    def test_vector_alone_prints_not_implemented(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["reindex", "--vector"])
        assert "not yet implemented" in result.output.lower()

    def test_vector_with_lexical_exits_zero(self) -> None:
        runner = CliRunner()
        with _patched_lexical():
            result = runner.invoke(cli, ["reindex", "--lexical", "--vector"])
        assert result.exit_code == 0, result.output


# ── index_state updated after success ─────────────────────────────────────────


@pytest.mark.unit
class TestReindexIndexState:
    def test_index_state_updated_calls_build_fts(self) -> None:
        """build_fts_index is responsible for calling mark_updated; verify it is called."""
        from pathlib import Path

        runner = CliRunner()
        with (
            patch("cerebra.cli.main._get_vault", return_value=Path("/fake/vault")),
            patch("cerebra.storage.migrations.run_migrations"),
            patch("pathlib.Path.exists", return_value=True),
            patch("cerebra.storage.db.connect") as mc,
            patch("cerebra.storage.lexical.build_fts_index", return_value=10) as mock_build,
        ):
            mc.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = [10]
            result = runner.invoke(cli, ["reindex", "--lexical"])
        assert result.exit_code == 0
        mock_build.assert_called_once()

    def test_index_state_db_path_passed_to_build(self) -> None:
        """build_fts_index receives the vault's data/cerebra.db path."""
        from pathlib import Path

        runner = CliRunner()
        expected_db = Path("/fake/vault/data/cerebra.db")
        with (
            patch("cerebra.cli.main._get_vault", return_value=Path("/fake/vault")),
            patch("cerebra.storage.migrations.run_migrations"),
            patch("pathlib.Path.exists", return_value=True),
            patch("cerebra.storage.db.connect") as mc,
            patch("cerebra.storage.lexical.build_fts_index", return_value=10) as mock_build,
        ):
            mc.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = [10]
            runner.invoke(cli, ["reindex", "--lexical"])
        mock_build.assert_called_once_with(expected_db)
