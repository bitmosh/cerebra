"""
Cerebra CLI — entry point for all `cerebra` commands.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from cerebra.vault.init import VaultAlreadyExistsError, init_vault

_DEFAULT_VAULT_ENV = "CEREBRA_VAULT"


def _resolve_vault(vault_override: str | None) -> Path:
    """Resolve vault path from --vault flag or CEREBRA_VAULT env var."""
    raw = vault_override or os.environ.get(_DEFAULT_VAULT_ENV)
    if not raw:
        raise click.ClickException("No vault specified. Use --vault <path> or set CEREBRA_VAULT.")
    return Path(raw)


@click.group()
@click.version_option(version="0.0.0", prog_name="cerebra")
def cli() -> None:
    """Cerebra — local-first cognitive runtime."""


@cli.command()
@click.argument("path", type=click.Path())
@click.option("--force", is_flag=True, default=False, help="Re-init an existing vault.")
def init(path: str, force: bool) -> None:
    """Initialize a Cerebra vault at PATH."""
    target = Path(path)
    try:
        vault = init_vault(target, force=force)
        click.echo(f"Vault initialized at {vault}")
    except VaultAlreadyExistsError as e:
        raise click.ClickException(str(e)) from e
    except Exception as e:
        raise click.ClickException(f"Init failed: {e}") from e


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--vault", default=None, help="Vault path (or set CEREBRA_VAULT).")
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

    vault_path = _resolve_vault(vault)
    if not vault_path.exists():
        raise click.ClickException(f"Vault not found: {vault_path}")

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
