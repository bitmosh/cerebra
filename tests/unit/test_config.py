"""Unit tests for cerebra.config — vault resolution and config file I/O."""

from __future__ import annotations

from pathlib import Path

import pytest

import cerebra.config as cfg
from cerebra.config import VaultNotFoundError, get_config_vault, resolve_vault, set_config_vault


@pytest.fixture(autouse=True)
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect config dir to tmp_path so tests don't touch real ~/.config."""
    fake_config_dir = tmp_path / ".config" / "cerebra"
    monkeypatch.setattr(cfg, "_CONFIG_DIR", fake_config_dir)
    monkeypatch.setattr(cfg, "_CONFIG_FILE", fake_config_dir / "config.toml")
    # Clear CEREBRA_VAULT env so resolution chain tests are predictable
    monkeypatch.delenv("CEREBRA_VAULT", raising=False)


@pytest.mark.unit
class TestConfigFileIO:
    def test_get_config_vault_returns_none_when_no_file(self) -> None:
        assert get_config_vault() is None

    def test_set_and_get_vault(self) -> None:
        set_config_vault("/tmp/my-vault")
        assert get_config_vault() == "/tmp/my-vault"

    def test_set_vault_overwrites_previous(self) -> None:
        set_config_vault("/tmp/vault-a")
        set_config_vault("/tmp/vault-b")
        assert get_config_vault() == "/tmp/vault-b"

    def test_set_vault_creates_config_dir(self, tmp_path: Path) -> None:
        assert not cfg._CONFIG_DIR.exists()
        set_config_vault("/tmp/vault")
        assert cfg._CONFIG_FILE.exists()

    def test_config_file_is_valid_toml(self) -> None:
        import tomllib

        set_config_vault("/tmp/vault")
        with cfg._CONFIG_FILE.open("rb") as f:
            data = tomllib.load(f)
        assert data["defaults"]["vault"] == "/tmp/vault"

    def test_path_with_spaces_round_trips(self) -> None:
        path = "/home/user/my vaults/dev vault"
        set_config_vault(path)
        assert get_config_vault() == path


@pytest.mark.unit
class TestResolveVault:
    def test_flag_takes_highest_priority(self) -> None:
        set_config_vault("/from/toml")
        vault, source = resolve_vault("/from/flag")
        assert str(vault) == "/from/flag"
        assert "flag" in source

    def test_env_var_beats_toml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        set_config_vault("/from/toml")
        monkeypatch.setenv("CEREBRA_VAULT", "/from/env")
        vault, source = resolve_vault(None)
        assert str(vault) == "/from/env"
        assert "CEREBRA_VAULT" in source

    def test_toml_used_when_no_flag_or_env(self) -> None:
        set_config_vault("/from/toml")
        vault, source = resolve_vault(None)
        assert str(vault) == "/from/toml"
        assert "config.toml" in source

    def test_raises_when_nothing_configured(self) -> None:
        with pytest.raises(VaultNotFoundError) as exc:
            resolve_vault(None)
        msg = str(exc.value)
        assert "--vault" in msg
        assert "CEREBRA_VAULT" in msg
        assert "config set vault" in msg

    def test_flag_beats_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CEREBRA_VAULT", "/from/env")
        vault, source = resolve_vault("/from/flag")
        assert str(vault) == "/from/flag"
        assert "flag" in source


@pytest.mark.unit
class TestGitRepoGuard:
    def test_detects_git_repo_root(self, tmp_path: Path) -> None:
        from cerebra.cli.main import _is_inside_git_repo

        (tmp_path / ".git").mkdir()
        assert _is_inside_git_repo(tmp_path) is True

    def test_detects_path_inside_git_repo(self, tmp_path: Path) -> None:
        from cerebra.cli.main import _is_inside_git_repo

        (tmp_path / ".git").mkdir()
        subdir = tmp_path / "sub" / "deep"
        subdir.mkdir(parents=True)
        assert _is_inside_git_repo(subdir) is True

    def test_clean_path_not_flagged(self, tmp_path: Path) -> None:
        from cerebra.cli.main import _is_inside_git_repo

        # tmp_path has no .git in its ancestry (pytest uses /tmp)
        assert _is_inside_git_repo(tmp_path) is False


@pytest.mark.unit
class TestConfigCLI:
    def test_config_set_vault(self) -> None:
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "set", "vault", "/tmp/vault"])
        assert result.exit_code == 0
        assert get_config_vault() == "/tmp/vault"

    def test_config_get_vault(self) -> None:
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        set_config_vault("/tmp/vault")
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "get", "vault"])
        assert result.exit_code == 0
        assert "/tmp/vault" in result.output

    def test_config_get_all(self) -> None:
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        set_config_vault("/tmp/vault")
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "get"])
        assert result.exit_code == 0
        assert "vault" in result.output

    def test_config_get_unknown_key_errors(self) -> None:
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["config", "get", "unknown_key"])
        assert result.exit_code != 0

    def test_init_refuses_inside_git_repo(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        (tmp_path / ".git").mkdir()
        target = str(tmp_path / "vault")
        runner = CliRunner()
        result = runner.invoke(cli, ["init", target])
        assert result.exit_code != 0
        assert "git" in result.output.lower()

    def test_init_force_bypasses_git_guard(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        (tmp_path / ".git").mkdir()
        target = str(tmp_path / "vault")
        runner = CliRunner()
        result = runner.invoke(cli, ["init", "--force", target])
        assert result.exit_code == 0
