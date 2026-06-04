"""
Vault initialization — `cerebra init <path>`.

Creates the vault directory structure, runs migrations, writes governance
defaults, and emits the VaultCreated + ConfigLoaded inspector events.
"""

from __future__ import annotations

import time
from pathlib import Path

import yaml

from cerebra.governance.loader import write_defaults_to_vault
from cerebra.inspector.event import make_event
from cerebra.inspector.ndjson_log import NDJSONEventLog
from cerebra.inspector.sqlite_log import SQLiteEventLog
from cerebra.storage.migrations import run_migrations

# Directories created inside every vault
VAULT_SUBDIRS = [
    "data",
    "artifacts",
    "indexes",
    "exports",
    "events",
    "leeway",
    "constitutional",
]


class VaultAlreadyExistsError(Exception):
    pass


class VaultInitError(Exception):
    pass


def init_vault(path: Path, *, force: bool = False) -> Path:
    """
    Initialize a Cerebra vault at path.

    Args:
        path: target directory (created if not present)
        force: if True, re-init an existing vault (runs any pending migrations)

    Returns:
        Resolved vault path.

    Raises:
        VaultAlreadyExistsError: vault exists and force=False
        VaultInitError: init failed
    """
    vault = path.resolve()

    config_path = vault / "config.yaml"
    if config_path.exists() and not force:
        raise VaultAlreadyExistsError(f"Vault already exists at {vault}. Use --force to re-init.")

    # Create directory tree
    vault.mkdir(parents=True, exist_ok=True)
    for subdir in VAULT_SUBDIRS:
        (vault / subdir).mkdir(exist_ok=True)

    # Write config.yaml
    config = {
        "cerebra_version": "0.0.0",
        "schema_version": 1,
        "created_at": int(time.time()),
        "vault_path": str(vault),
    }
    config_path.write_text(yaml.dump(config, default_flow_style=False), encoding="utf-8")

    # Run migrations (creates inspector_events table)
    db_path = vault / "data" / "cerebra.db"
    applied = run_migrations(db_path)

    # Write governance defaults (leeway + constitutional YAML files)
    write_defaults_to_vault(vault)

    # Set up inspector logs
    sqlite_log = SQLiteEventLog(db_path)
    ndjson_log = NDJSONEventLog(vault / "events" / "system.ndjson")

    # Emit VaultCreated event
    vault_event = make_event(
        event_type="VaultCreated",
        actor="vault_init",
        summary=f"Vault initialized at {vault}",
        data={"vault_path": str(vault), "config": config},
        subject_id=str(vault),
    )
    sqlite_log.write(vault_event)
    ndjson_log.write(vault_event)

    # Emit MigrationRun events
    for version in applied:
        migration_event = make_event(
            event_type="MigrationRun",
            actor="vault_init",
            summary=f"Migration {version} applied",
            data={"migration_version": version},
        )
        sqlite_log.write(migration_event)
        ndjson_log.write(migration_event)

    # Emit ConfigLoaded events for governance files
    leeway_event = make_event(
        event_type="ConfigLoaded",
        actor="vault_init",
        summary="Leeway rules loaded",
        data={"config_type": "leeway", "source": "defaults"},
    )
    sqlite_log.write(leeway_event)
    ndjson_log.write(leeway_event)

    constitutional_event = make_event(
        event_type="ConfigLoaded",
        actor="vault_init",
        summary="Constitutional rules loaded",
        data={"config_type": "constitutional", "source": "defaults"},
    )
    sqlite_log.write(constitutional_event)
    ndjson_log.write(constitutional_event)

    return vault
