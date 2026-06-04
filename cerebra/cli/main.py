"""
Cerebra CLI — entry point for all `cerebra` commands.
"""

from __future__ import annotations

from pathlib import Path

import click

from cerebra.vault.init import VaultAlreadyExistsError, init_vault


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
