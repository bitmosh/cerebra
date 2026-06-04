"""Integration tests for vault init — uses temp vault fixture."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from cerebra.vault.init import VaultAlreadyExistsError, init_vault


@pytest.mark.integration
class TestVaultInit:
    def test_creates_expected_subdirectories(self, tmp_path: Path) -> None:
        vault = init_vault(tmp_path / "vault")
        expected = ["data", "artifacts", "indexes", "exports", "events", "leeway", "constitutional"]
        for d in expected:
            assert (vault / d).is_dir(), f"Missing subdir: {d}"

    def test_creates_config_yaml(self, tmp_path: Path) -> None:
        vault = init_vault(tmp_path / "vault")
        config_path = vault / "config.yaml"
        assert config_path.exists()

        import yaml

        config = yaml.safe_load(config_path.read_text())
        assert config["cerebra_version"] == "0.0.0"

    def test_creates_sqlite_database(self, tmp_path: Path) -> None:
        vault = init_vault(tmp_path / "vault")
        db = vault / "data" / "cerebra.db"
        assert db.exists()

    def test_sqlite_has_events_table(self, tmp_path: Path) -> None:
        vault = init_vault(tmp_path / "vault")
        db = vault / "data" / "cerebra.db"
        conn = sqlite3.connect(db)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        conn.close()
        assert "inspector_events" in tables

    def test_writes_vault_created_event_to_sqlite(self, tmp_path: Path) -> None:
        vault = init_vault(tmp_path / "vault")
        conn = sqlite3.connect(vault / "data" / "cerebra.db")
        rows = conn.execute(
            "SELECT event_type FROM inspector_events WHERE event_type = 'VaultCreated'"
        ).fetchall()
        conn.close()
        assert len(rows) == 1

    def test_writes_events_to_ndjson_log(self, tmp_path: Path) -> None:
        vault = init_vault(tmp_path / "vault")
        log_file = vault / "events" / "system.ndjson"
        assert log_file.exists()
        lines = log_file.read_text().splitlines()
        assert len(lines) >= 1
        for line in lines:
            parsed = json.loads(line)
            assert "event_id" in parsed

    def test_writes_governance_yaml_files(self, tmp_path: Path) -> None:
        vault = init_vault(tmp_path / "vault")
        assert (vault / "leeway" / "default.yaml").exists()
        assert (vault / "constitutional" / "default.yaml").exists()

    def test_leeway_yaml_has_15_rules(self, tmp_path: Path) -> None:
        vault = init_vault(tmp_path / "vault")
        import yaml

        rules = yaml.safe_load((vault / "leeway" / "default.yaml").read_text())
        assert len(rules) == 15

    def test_constitutional_yaml_has_5_rules(self, tmp_path: Path) -> None:
        vault = init_vault(tmp_path / "vault")
        import yaml

        rules = yaml.safe_load((vault / "constitutional" / "default.yaml").read_text())
        assert len(rules) == 5

    def test_raises_on_double_init_without_force(self, tmp_path: Path) -> None:
        init_vault(tmp_path / "vault")
        with pytest.raises(VaultAlreadyExistsError):
            init_vault(tmp_path / "vault")

    def test_force_reinit_succeeds(self, tmp_path: Path) -> None:
        init_vault(tmp_path / "vault")
        vault = init_vault(tmp_path / "vault", force=True)
        assert vault.exists()

    def test_config_loaded_events_emitted(self, tmp_path: Path) -> None:
        vault = init_vault(tmp_path / "vault")
        conn = sqlite3.connect(vault / "data" / "cerebra.db")
        rows = conn.execute(
            "SELECT event_type FROM inspector_events WHERE event_type = 'ConfigLoaded'"
        ).fetchall()
        conn.close()
        # expect 2: one for leeway, one for constitutional
        assert len(rows) == 2
