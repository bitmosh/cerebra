#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
cerebra-relay.py — Cerebra → Lattica hub relay agent.

Subscribes to cerebra/** on the local fossic store and relays
agent-trace, lattice, and bot events to the hub. graph/* and
control are excluded (graph/* is hub-direct via exporter.py;
control is local-only posture stream).

Run: python cerebra-relay.py

Env vars:
  CEREBRA_VAULT          — path to vault root (fallback: ~/.config/cerebra/config.toml)
  CEREBRA_PLATFORM_STORE — path to hub fossic store (default: ~/.lattica/fossic/store.db)
"""

from __future__ import annotations

import logging
import os
import sys
import tomllib
from pathlib import Path

from fossic import RelayAgent, RelayConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-28s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("cerebra.relay")


# ── Stream prefix constants ────────────────────────────────────────────────────

_AGENT_TRACE_PREFIX = "cerebra/agent-trace/"
_LATTICE_PREFIX = "cerebra/lattice/"
_BOT_PREFIX = "cerebra/bot/"
_GRAPH_PREFIX = "cerebra/graph/"
_CONTROL_STREAM = "cerebra/control"


class CerebraRelayAgent(RelayAgent):
    def _should_relay(self, event) -> bool:
        if event.stream_id.startswith(_AGENT_TRACE_PREFIX):
            return True
        if event.stream_id.startswith(_LATTICE_PREFIX):
            return True
        if event.stream_id.startswith(_BOT_PREFIX):
            return True  # post-fold-in only; safe to relay when stream exists
        if event.stream_id.startswith(_GRAPH_PREFIX):
            return False  # hub-direct via exporter.py — skip to prevent double-write
        if event.stream_id == _CONTROL_STREAM:
            return False  # local-only posture stream
        return False


# ── Path resolution ────────────────────────────────────────────────────────────

def _resolve_vault_path() -> Path:
    """Resolve vault path via CEREBRA_VAULT env var or ~/.config/cerebra/config.toml."""
    env = os.environ.get("CEREBRA_VAULT")
    if env:
        return Path(env).expanduser()

    config_file = Path.home() / ".config" / "cerebra" / "config.toml"
    if config_file.exists():
        with config_file.open("rb") as f:
            data = tomllib.load(f)
        vault = data.get("defaults", {}).get("vault")
        if vault:
            return Path(str(vault)).expanduser()

    logger.error(
        "No vault configured. Set CEREBRA_VAULT env var or run: cerebra config set vault <path>"
    )
    sys.exit(1)


def _resolve_hub_store_path() -> Path:
    """Resolve hub store path via CEREBRA_PLATFORM_STORE env var or default."""
    env = os.environ.get("CEREBRA_PLATFORM_STORE")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".lattica" / "fossic" / "store.db"


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    vault_path = _resolve_vault_path()
    local_store_path = vault_path / ".fossic" / "store.db"
    hub_store_path = _resolve_hub_store_path()

    logger.info("Cerebra relay agent starting")
    logger.info("  local store : %s", local_store_path)
    logger.info("  hub store   : %s", hub_store_path)

    config = RelayConfig(
        local_store_path=str(local_store_path),
        hub_store_path=str(hub_store_path),
        source_prefix="cerebra",
        subscribe_pattern="cerebra/**",
        relay_filter=set(),  # stream-based; handled by CerebraRelayAgent._should_relay
    )

    CerebraRelayAgent(config).run()


if __name__ == "__main__":
    main()
