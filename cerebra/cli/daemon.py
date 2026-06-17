"""
cerebra serve — lightweight HTTP daemon for tile control surface.

Exposes 4 endpoints on 127.0.0.1:<port> (default 7432):
    GET  /status     — posture, active session, cycle running, cycle count
    POST /posture    — { "state": "hold" | "auto" }
    POST /cycles     — { "config_name": "...", "goal": "..." }
    POST /checkpoint — snapshot current session state to fossic

PostureChanged events emit to cerebra/control (global, not per-session).
CheckpointSaved events emit to cerebra/agent-trace/<session_id>.
"""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import threading
import time
from pathlib import Path
from typing import Any

import click


# ── Daemon state ──────────────────────────────────────────────────────────────


class DaemonState:
    """Shared mutable state across HTTP handler threads and the cycle thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.posture: str = "auto"
        self.cycle_thread: threading.Thread | None = None
        self.active_session_id: str | None = None
        self.cycle_count: int = 0
        self.last_outcome: str | None = None

    def is_cycle_running(self) -> bool:
        with self._lock:
            return self.cycle_thread is not None and self.cycle_thread.is_alive()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "posture": self.posture,
                "cycle_running": self.cycle_thread is not None and self.cycle_thread.is_alive(),
                "active_session_id": self.active_session_id,
                "cycle_count": self.cycle_count,
                "last_outcome": self.last_outcome,
            }


# ── Cycle worker ──────────────────────────────────────────────────────────────


def _run_cycle(
    state: DaemonState,
    config_name: str,
    goal: str,
    vault_path: Path,
    db_path: Path,
    store: Any,
) -> None:
    """Cycle worker executed in a background thread."""
    from cerebra.cognition.cycle_config import CycleConfigLoader, CycleConfigValidationError
    from cerebra.cognition.cycle_runtime import CycleRuntime
    from cerebra.cognition.llm_adapter import OllamaDirectAdapter
    from cerebra.cognition.session import SessionManager

    try:
        loader = CycleConfigLoader()
        cycle_config = loader.load(config_name, vault_path)
    except (FileNotFoundError, CycleConfigValidationError, Exception) as exc:
        with state._lock:
            state.last_outcome = f"config_error: {exc}"
            state.cycle_thread = None
        return

    try:
        manager = SessionManager(db_path=db_path, store=store)
        session, opened_event_id = manager.open_session(
            goal=goal,
            cycle_config=config_name,
            vault_path=vault_path,
        )
        with state._lock:
            state.active_session_id = session.session_id

        llm = OllamaDirectAdapter()
        runtime = CycleRuntime(
            config=cycle_config,
            session=session,
            db_path=db_path,
            store=store,
            llm=llm,
            opened_event_id=opened_event_id,
            install_signal_handlers=False,
        )
        result = runtime.run()

        with state._lock:
            state.cycle_count += 1
            state.last_outcome = result.outcome
            state.cycle_thread = None
    except Exception as exc:
        with state._lock:
            state.last_outcome = f"runtime_error: {exc}"
            state.cycle_thread = None


# ── Checkpoint ────────────────────────────────────────────────────────────────


def _checkpoint(
    state: DaemonState,
    db_path: Path,
    store: Any,
) -> dict[str, Any]:
    """Snapshot current session state; emit CheckpointSaved to fossic."""
    from cerebra.cognition.continuation_bundle import BundleDistiller, write_bundle
    from cerebra.cognition.truth_tower import TruthTower
    from cerebra.cognition.working_memory import WorkingMemory

    with state._lock:
        session_id = state.active_session_id

    if session_id is None:
        return {"error": "no active session"}

    try:
        wm = WorkingMemory(db_path, session_id)
        tower = TruthTower(db_path, session_id)
        wm_items = wm.to_dict()
        tower_field = tower.to_tower_field() or {}

        distiller = BundleDistiller()
        bundle = distiller.distill(
            parent_session_id=session_id,
            goal="",
            recursion_depth=0,
            tower_data=tower_field,
        )
        write_bundle(db_path, bundle)

        wm_count = wm_items.get("total_item_count", 0)
        t1_count = len(tower_field.get("t1_items", []))
        t2_count = len(tower_field.get("t2_items", []))

        store.append(
            stream_id=f"cerebra/agent-trace/{session_id}",
            event_type="CheckpointSaved",
            payload={
                "session_id": session_id,
                "bundle_id": bundle.bundle_id,
                "wm_item_count": wm_count,
                "t1_count": t1_count,
                "t2_count": t2_count,
                "checkpointed_at": int(time.time() * 1000),
            },
            indexed_tags={"session_id": session_id},
        )
        return {"bundle_id": bundle.bundle_id, "session_id": session_id}
    except Exception as exc:
        return {"error": str(exc)}


# ── HTTP handler factory ──────────────────────────────────────────────────────


def _make_handler(
    daemon_state: DaemonState,
    vault_path: Path,
    db_path: Path,
    store: Any,
) -> type:

    class Handler(http.server.BaseHTTPRequestHandler):
        state = daemon_state

        def _send_json(self, code: int, body: dict[str, Any]) -> None:
            payload = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload)

        def _read_json(self) -> dict[str, Any] | None:
            length = int(self.headers.get("Content-Length", 0))
            if not length:
                return {}
            try:
                return json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                return None

        def do_GET(self) -> None:
            if self.path == "/status":
                self._send_json(200, self.state.snapshot())
            else:
                self._send_json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path == "/posture":
                self._handle_posture()
            elif self.path == "/cycles":
                self._handle_cycles()
            elif self.path == "/checkpoint":
                self._handle_checkpoint()
            else:
                self._send_json(404, {"error": "not found"})

        def _handle_posture(self) -> None:
            body = self._read_json()
            if body is None:
                self._send_json(400, {"error": "invalid JSON"})
                return
            new_posture = body.get("state")
            if new_posture not in ("auto", "hold"):
                self._send_json(400, {"error": "state must be 'auto' or 'hold'"})
                return
            with self.state._lock:
                self.state.posture = new_posture
            store.append(
                stream_id="cerebra/control",
                event_type="PostureChanged",
                payload={
                    "posture": new_posture,
                    "changed_at": int(time.time() * 1000),
                },
            )
            self._send_json(200, {"posture": new_posture})

        def _handle_cycles(self) -> None:
            body = self._read_json()
            if body is None:
                self._send_json(400, {"error": "invalid JSON"})
                return
            config_name = body.get("config_name", "")
            goal = body.get("goal", "")
            if not config_name or not goal:
                self._send_json(400, {"error": "config_name and goal are required"})
                return

            with self.state._lock:
                if self.state.posture == "hold":
                    self._send_json(409, {"error": "posture is HOLD; release before triggering"})
                    return
                if self.state.cycle_thread is not None and self.state.cycle_thread.is_alive():
                    self._send_json(409, {"error": "cycle already running"})
                    return
                t = threading.Thread(
                    target=_run_cycle,
                    args=(self.state, config_name, goal, vault_path, db_path, store),
                    daemon=True,
                )
                self.state.cycle_thread = t

            t.start()
            self._send_json(202, {"status": "accepted", "config_name": config_name})

        def _handle_checkpoint(self) -> None:
            result = _checkpoint(self.state, db_path, store)
            code = 200 if "error" not in result else 409
            self._send_json(code, result)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            pass

    return Handler


# ── Threaded server ───────────────────────────────────────────────────────────


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


# ── CLI command ───────────────────────────────────────────────────────────────


@click.command("serve")
@click.option("--vault", default=None, help="Vault path (overrides env + config).")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address.")
@click.option("--port", default=7432, show_default=True, help="Listen port.")
def serve(vault: str | None, host: str, port: int) -> None:
    """Run Cerebra as a persistent HTTP daemon (tile control surface).

    Endpoints (all on 127.0.0.1:<port>):
      GET  /status     posture, session, cycle state
      POST /posture    { "state": "hold" | "auto" }
      POST /cycles     { "config_name": "...", "goal": "..." }
      POST /checkpoint snapshot session state to fossic
    """
    import signal as _signal
    import sys

    from cerebra.config import VaultNotFoundError, resolve_vault
    from cerebra.storage.fossic_store import FossicStore
    from cerebra.storage.migrations import run_migrations

    # ── resolve vault ─────────────────────────────────────────────────────────
    try:
        vault_path, _ = resolve_vault(vault)
    except VaultNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    if not vault_path.exists():
        raise click.ClickException(f"Vault not found: {vault_path}")

    db_path = vault_path / "data" / "cerebra.db"
    if not db_path.exists():
        raise click.ClickException(
            f"Vault at {vault_path} has no database. Run 'cerebra init {vault_path}' first."
        )

    try:
        run_migrations(db_path)
    except Exception as exc:
        raise click.ClickException(f"Migration failed: {exc}") from exc

    # ── open fossic store ─────────────────────────────────────────────────────
    platform_env = os.environ.get("CEREBRA_PLATFORM_STORE")
    if platform_env:
        store = FossicStore.at_platform_path(Path(platform_env).expanduser())
    else:
        store = FossicStore(vault_path)

    # ── start server ──────────────────────────────────────────────────────────
    state = DaemonState()
    handler_cls = _make_handler(state, vault_path, db_path, store)

    try:
        server = _ThreadedHTTPServer((host, port), handler_cls)
    except OSError as exc:
        raise click.ClickException(f"Could not bind {host}:{port} — {exc}") from exc

    shutdown_event = threading.Event()

    def _handle_shutdown(signum: int, frame: Any) -> None:
        click.echo("\nShutting down...")
        shutdown_event.set()
        server.shutdown()

    _signal.signal(_signal.SIGINT, _handle_shutdown)
    _signal.signal(_signal.SIGTERM, _handle_shutdown)

    click.echo(f"cerebra serve  vault={vault_path}  {host}:{port}")
    click.echo("Endpoints: GET /status  POST /posture  POST /cycles  POST /checkpoint")

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    shutdown_event.wait()
    server_thread.join(timeout=5)
    sys.exit(0)
