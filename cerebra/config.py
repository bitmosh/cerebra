# SPDX-License-Identifier: Apache-2.0
"""
Cerebra user configuration — manages ~/.config/cerebra/config.toml.

Vault resolution order (highest to lowest priority):
  1. --vault <path> CLI flag
  2. CEREBRA_VAULT environment variable
  3. ~/.config/cerebra/config.toml  [defaults] vault = "..."
  4. Error listing all three options

Uses stdlib tomllib (Python 3.11+) for reading.
Writes are handled with a minimal formatter — no external toml dep needed.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

_CONFIG_DIR = Path.home() / ".config" / "cerebra"
_CONFIG_FILE = _CONFIG_DIR / "config.toml"


class VaultNotFoundError(Exception):
    pass


def get_config_vault() -> str | None:
    """Read vault path from config file. Returns None if not set."""
    if not _CONFIG_FILE.exists():
        return None
    with _CONFIG_FILE.open("rb") as f:
        data = tomllib.load(f)
    val = data.get("defaults", {}).get("vault")
    return str(val) if val is not None else None


def set_config_vault(path: str) -> None:
    """Write vault path to config file, preserving other keys."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict[str, str]] = {}
    if _CONFIG_FILE.exists():
        with _CONFIG_FILE.open("rb") as f:
            raw = tomllib.load(f)
        # Only carry forward string-valued sections for safe round-trip
        for section, values in raw.items():
            if isinstance(values, dict):
                existing[section] = {k: str(v) for k, v in values.items()}
    if "defaults" not in existing:
        existing["defaults"] = {}
    existing["defaults"]["vault"] = path
    _CONFIG_FILE.write_text(_serialize_toml(existing), encoding="utf-8")


def _serialize_toml(data: dict[str, dict[str, str]]) -> str:
    """Minimal TOML serializer for shallow string-valued section dicts."""
    lines: list[str] = []
    for section, values in data.items():
        lines.append(f"[{section}]")
        for k, v in values.items():
            escaped = v.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k} = "{escaped}"')
        lines.append("")
    return "\n".join(lines)


def get_all_config() -> dict[str, object]:
    """Return full config file contents, or empty dict if no file."""
    if not _CONFIG_FILE.exists():
        return {}
    with _CONFIG_FILE.open("rb") as f:
        return dict(tomllib.load(f))


def resolve_vault(flag_value: str | None = None) -> tuple[Path, str]:
    """
    Resolve vault path using the priority chain.

    Returns:
        (vault_path, source_description)

    Raises:
        VaultNotFoundError: if no vault is configured via any source
    """
    if flag_value:
        return Path(flag_value), "--vault flag"

    env = os.environ.get("CEREBRA_VAULT")
    if env:
        return Path(env), "CEREBRA_VAULT env var"

    toml_vault = get_config_vault()
    if toml_vault:
        return Path(toml_vault), "~/.config/cerebra/config.toml"

    raise VaultNotFoundError(
        "No vault specified. Use one of:\n"
        "  --vault <path>\n"
        "  CEREBRA_VAULT=<path> cerebra ...\n"
        "  cerebra config set vault <path>"
    )
