"""
Cerebra CLI — entry point for all `cerebra` commands.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from cerebra.config import VaultNotFoundError, resolve_vault
from cerebra.vault.init import VaultAlreadyExistsError, init_vault


def _is_inside_git_repo(path: Path) -> bool:
    """Return True if path or any ancestor contains a .git/ directory."""
    check = path.resolve()
    while True:
        if (check / ".git").exists():
            return True
        parent = check.parent
        if parent == check:
            return False
        check = parent


def _get_vault(vault_flag: str | None) -> Path:
    """Resolve vault via priority chain; wrap VaultNotFoundError as ClickException."""
    try:
        vault_path, _ = resolve_vault(vault_flag)
    except VaultNotFoundError as e:
        raise click.ClickException(str(e)) from e
    if not vault_path.exists():
        raise click.ClickException(f"Vault not found: {vault_path}")
    return vault_path


@click.group()
@click.version_option(version="0.0.0", prog_name="cerebra")
def cli() -> None:
    """Cerebra — local-first cognitive runtime."""


# ── init ─────────────────────────────────────────────────────────────────────


@cli.command()
@click.argument("path", type=click.Path())
@click.option(
    "--force", is_flag=True, default=False, help="Re-init existing vault / skip git guard."
)
def init(path: str, force: bool) -> None:
    """Initialize a Cerebra vault at PATH."""
    target = Path(path).resolve()

    if not force and _is_inside_git_repo(target):
        raise click.ClickException(
            f"{target} is inside a git repository. "
            "Initializing a vault here risks committing vault data. "
            "Use --force to override, or choose a path outside the repo."
        )

    try:
        vault = init_vault(target, force=force)
        click.echo(f"Vault initialized at {vault}")
    except VaultAlreadyExistsError as e:
        raise click.ClickException(str(e)) from e
    except Exception as e:
        raise click.ClickException(f"Init failed: {e}") from e


# ── ingest ────────────────────────────────────────────────────────────────────


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--vault", default=None, help="Vault path (overrides env + config).")
@click.option("--dry-run", is_flag=True, default=False, help="Discover files but do not write.")
@click.option(
    "--exclude",
    multiple=True,
    metavar="PATTERN",
    help="Exclude pattern (repeatable). Overrides defaults.",
)
@click.option(
    "--extensions",
    default=None,
    help="Comma-separated file extensions to include, e.g. '.md,.txt'.",
)
@click.option("--json", "output_json", is_flag=True, default=False, help="Output report as JSON.")
def ingest(
    path: str,
    vault: str | None,
    dry_run: bool,
    exclude: tuple[str, ...],
    extensions: str | None,
    output_json: bool,
) -> None:
    """Ingest files at PATH into the vault."""
    from cerebra.ingest.pipeline import ingest_path

    vault_path = _get_vault(vault)

    exts: frozenset[str] | None = None
    if extensions:
        exts = frozenset(e.strip() for e in extensions.split(","))

    exclude_patterns: list[str] | None = list(exclude) if exclude else None

    try:
        report = ingest_path(
            vault_path=vault_path,
            target=Path(path),
            dry_run=dry_run,
            exclude_patterns=exclude_patterns,
            extensions=exts,
        )
    except Exception as e:
        raise click.ClickException(f"Ingest failed: {e}") from e

    if output_json:
        click.echo(json.dumps(report.as_dict(), indent=2))
        return

    prefix = "[dry-run] " if dry_run else ""
    click.echo(f"{prefix}Ingest complete:")
    click.echo(f"  Found:    {report.sources_found}")
    click.echo(f"  New:      {report.sources_new}")
    click.echo(f"  Changed:  {report.sources_changed}")
    click.echo(f"  Skipped:  {report.sources_skipped}")
    click.echo(f"  Failed:   {report.sources_failed}")
    click.echo(f"  Chunks:   {report.chunks_created}")
    click.echo(f"  Records:  {report.records_created}")
    if report.errors:
        click.echo("Errors:")
        for err in report.errors:
            click.echo(f"  {err}", err=True)


# ── config ────────────────────────────────────────────────────────────────────


@cli.group()
def config() -> None:
    """Manage Cerebra configuration (~/.config/cerebra/config.toml)."""


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a configuration value. Supported keys: vault."""
    from cerebra.config import set_config_vault

    if key == "vault":
        set_config_vault(value)
        click.echo(f"vault = {value}")
    else:
        raise click.ClickException(f"Unknown config key: {key!r}. Supported: vault")


@config.command("get")
@click.argument("key", required=False, default=None)
def config_get(key: str | None) -> None:
    """Show configuration value(s). Omit KEY to show all."""
    from cerebra.config import get_all_config, resolve_vault

    if key == "vault":
        try:
            vault_path, source = resolve_vault(None)
            click.echo(f"vault = {vault_path}  (from {source})")
        except VaultNotFoundError:
            click.echo("vault = (not set)")
    elif key is None:
        data = get_all_config()
        if not data:
            click.echo("(no configuration)")
            return
        for section, values in data.items():
            click.echo(f"[{section}]")
            if isinstance(values, dict):
                for k, v in values.items():
                    click.echo(f"  {k} = {v}")
    else:
        raise click.ClickException(f"Unknown config key: {key!r}. Supported: vault")


# ── status ────────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--vault", default=None, help="Vault path (overrides env + config).")
def status(vault: str | None) -> None:
    """Show vault status summary."""
    import time

    from cerebra.storage.db import connect
    from cerebra.storage.migrations import run_migrations

    try:
        vault_path, source = resolve_vault(vault)
    except VaultNotFoundError as e:
        raise click.ClickException(str(e)) from e

    db_path = vault_path / "data" / "cerebra.db"
    if not db_path.exists():
        raise click.ClickException(
            f"Vault at {vault_path} has no database. Run 'cerebra init {vault_path}' first."
        )

    run_migrations(db_path)
    conn = connect(db_path)

    try:
        source_count = conn.execute(
            "SELECT COUNT(*) FROM sources WHERE lifecycle_state='active'"
        ).fetchone()[0]
        chunk_count = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE lifecycle_state='active'"
        ).fetchone()[0]
        record_count = conn.execute(
            "SELECT COUNT(*) FROM memory_records WHERE lifecycle_state='active'"
        ).fetchone()[0]
        last_ingest_ts = conn.execute("SELECT MAX(ingested_at) FROM sources").fetchone()[0]
        schema_version = conn.execute("SELECT MAX(version) FROM applied_migrations").fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()

    last_ingest = (
        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_ingest_ts))
        if last_ingest_ts
        else "never"
    )

    click.echo(f"Vault:          {vault_path}")
    click.echo(f"  Source:       {source}")
    click.echo(f"  Sources:      {source_count} active")
    click.echo(f"  Chunks:       {chunk_count} active")
    click.echo(f"  Records:      {record_count} active")
    click.echo(f"  Last ingest:  {last_ingest}")
    click.echo(f"  Schema ver:   {schema_version}")
    click.echo(f"  Journal mode: {journal_mode}")
