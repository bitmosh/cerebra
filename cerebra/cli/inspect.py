"""
cerebra inspect — runtime observability commands.

Event sources:
  FossicStore (.fossic/store.db)    — cycle events: CycleStarted, SignalEvaluated,
                                       ClutchDecisionMade, LeewayGrantApplied, etc.
  inspector_events (cerebra.db)     — retrieval, WM, SKU, graph export events.
  runtime_sessions (cerebra.db)     — cognitive session rows.
  retrieval_traces (cerebra.db)     — one row per retrieval query.
  memory_records (cerebra.db)       — ingested memory records + SKU.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import click

from cerebra.config import VaultNotFoundError, resolve_vault
from cerebra.storage.db import connect
from cerebra.storage.migrations import run_migrations


# ── shared helpers ────────────────────────────────────────────────────────────


def _get_db(vault_flag: str | None) -> tuple[Path, Path]:
    """Resolve vault, run migrations, return (vault_path, db_path)."""
    import sys

    try:
        vault_path, _ = resolve_vault(vault_flag)
    except VaultNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)
    db_path = vault_path / "data" / "cerebra.db"
    if not db_path.exists():
        click.echo(f"Error: vault database not found at {db_path}", err=True)
        sys.exit(2)
    try:
        run_migrations(db_path)
    except Exception as e:
        click.echo(f"Error: migration failed: {e}", err=True)
        sys.exit(2)
    return vault_path, db_path


def _fmt_ts(ts: int | None) -> str:
    if ts is None:
        return "—"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def _ago(ts: int | None) -> str:
    if ts is None:
        return "—"
    delta = int(time.time()) - ts
    if delta < 0:
        return "just now"
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


def _parse_last(window: str | None) -> int | None:
    """Parse '1h', '24h', '7d', '30m' into seconds; return None if no window."""
    if window is None:
        return None
    w = window.strip().lower()
    try:
        if w.endswith("h"):
            return int(w[:-1]) * 3600
        if w.endswith("d"):
            return int(w[:-1]) * 86400
        if w.endswith("m"):
            return int(w[:-1]) * 60
    except ValueError:
        pass
    raise click.BadParameter(
        f"Cannot parse time window {window!r}. Use e.g. '1h', '24h', '30m', '7d'.",
        param_hint="--last",
    )


def _render_event_brief(ev: dict[str, Any]) -> None:
    """Print one inspector_events row in a compact two-token line."""
    ts = _fmt_ts(ev.get("timestamp"))
    etype = ev.get("event_type", "?")
    summary = (ev.get("summary") or "")[:80]
    click.echo(f"  {ts}  {etype:<36}  {summary}")


def _render_fossic_event_brief(ev: dict[str, Any]) -> None:
    """Print one FossicStore event dict in compact form."""
    p = ev.get("payload", {})
    etype = ev.get("event_type", "?")
    cycle = p.get("cycle_id", "—")
    step = p.get("step_id", "—")
    click.echo(f"  {etype:<36}  cycle={cycle}  step={step}")


def _fossic_store_for(vault_path: Path):  # type: ignore[return]
    """Return FossicStore for vault, or None if fossic db not present."""
    from cerebra.storage.fossic_store import FossicStore

    fossic_db = vault_path / ".fossic" / "store.db"
    if not fossic_db.exists():
        return None
    return FossicStore(vault_path)


def _session_events_from_fossic(vault_path: Path, session_id: str) -> list[dict[str, Any]]:
    """Return all FossicStore events for a session's agent-trace stream."""
    store = _fossic_store_for(vault_path)
    if store is None:
        return []
    stream = f"cerebra/agent-trace/{session_id}"
    return store.read_events(stream_id=stream)


def _cycle_events_from_fossic(
    vault_path: Path, session_id: str, cycle_id: str
) -> list[dict[str, Any]]:
    """Return FossicStore events filtered to a specific cycle_id."""
    all_evs = _session_events_from_fossic(vault_path, session_id)
    return [e for e in all_evs if e.get("payload", {}).get("cycle_id") == cycle_id]


# ── inspect group ─────────────────────────────────────────────────────────────


@click.group()
def inspect() -> None:
    """Inspect runtime events, sessions, cycles, memory, and retrievals."""


# ── inspect session ───────────────────────────────────────────────────────────


@inspect.group("session")
def inspect_session() -> None:
    """Inspect cognitive runtime sessions."""


@inspect_session.command("list")
@click.option("--vault", default=None, help="Vault path.")
@click.option("--limit", default=20, show_default=True, help="Max sessions to list.")
@click.option("--json", "output_json", is_flag=True, default=False)
def session_list(vault: str | None, limit: int, output_json: bool) -> None:
    """List recent cognitive runtime sessions."""
    _, db_path = _get_db(vault)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT session_id, goal, cycle_config, state, opened_at, cycles_run, steps_run "
            "FROM runtime_sessions ORDER BY opened_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    data = [dict(r) for r in rows]
    if output_json:
        click.echo(json.dumps(data, indent=2))
        return

    if not data:
        click.echo("No sessions found.")
        return

    click.echo(f"{'Session':<22}  {'State':<10}  {'Cycles':>6}  {'Opened':<20}  Goal")
    click.echo(f"{'-------':<22}  {'-----':<10}  {'------':>6}  {'------':<20}  ----")
    for r in data:
        goal = (r.get("goal") or "")[:50]
        click.echo(
            f"{r['session_id']:<22}  {r['state']:<10}  {r.get('cycles_run', 0):>6}"
            f"  {_fmt_ts(r.get('opened_at')):<20}  {goal}"
        )


@inspect_session.command("show")
@click.argument("session_id")
@click.option("--vault", default=None, help="Vault path.")
@click.option("--events", is_flag=True, default=False, help="Show full event list.")
@click.option("--json", "output_json", is_flag=True, default=False)
def session_show(
    session_id: str, vault: str | None, events: bool, output_json: bool
) -> None:
    """Show summary (or events) for SESSION_ID."""
    import sys

    vault_path, db_path = _get_db(vault)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM runtime_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()

    if row is None:
        click.echo(f"Session {session_id!r} not found.", err=True)
        sys.exit(2)

    fossic_evs = _session_events_from_fossic(vault_path, session_id)

    if events:
        if output_json:
            click.echo(json.dumps([e["payload"] | {"event_type": e["event_type"]} for e in fossic_evs], indent=2))
            return
        click.echo(f"Events for session {session_id}  ({len(fossic_evs)} total):")
        for ev in fossic_evs:
            _render_fossic_event_brief(ev)
        return

    r = dict(row)
    if output_json:
        r["event_count"] = len(fossic_evs)
        click.echo(json.dumps(r, indent=2))
        return

    click.echo(f"Session:      {session_id}")
    click.echo(f"Goal:         {r.get('goal', '—')}")
    click.echo(f"Config:       {r.get('cycle_config', '—')}")
    click.echo(f"State:        {r.get('state', '—')}")
    click.echo(f"Opened:       {_fmt_ts(r.get('opened_at'))}  ({_ago(r.get('opened_at'))})")
    click.echo(f"Cycles run:   {r.get('cycles_run', 0)}")
    click.echo(f"Steps run:    {r.get('steps_run', 0)}")
    if r.get("final_outcome"):
        click.echo(f"Final outcome:{r['final_outcome']}")
    click.echo(f"Events:       {len(fossic_evs)} (FossicStore stream)")
    click.echo(f"\nUse --events to list all events for this session.")


# ── inspect cycle ─────────────────────────────────────────────────────────────


@inspect.group("cycle")
def inspect_cycle() -> None:
    """Inspect cognitive cycles."""


@inspect_cycle.command("show")
@click.argument("cycle_id")
@click.option("--vault", default=None, help="Vault path.")
@click.option("--steps", is_flag=True, default=False, help="Show step-by-step trace.")
@click.option("--signals", is_flag=True, default=False, help="Show signal evaluations.")
@click.option("--clutch", is_flag=True, default=False, help="Show clutch decisions.")
@click.option("--json", "output_json", is_flag=True, default=False)
def cycle_show(
    cycle_id: str,
    vault: str | None,
    steps: bool,
    signals: bool,
    clutch: bool,
    output_json: bool,
) -> None:
    """Show cycle CYCLE_ID (summary, or specific view with --steps/--signals/--clutch)."""
    import sys

    vault_path, db_path = _get_db(vault)

    # Find session_id via cycle_episode_records
    with connect(db_path) as conn:
        ep_row = conn.execute(
            "SELECT runtime_session_id FROM cycle_episode_records WHERE cycle_id = ? LIMIT 1",
            (cycle_id,),
        ).fetchone()

    if ep_row is None:
        click.echo(
            f"Cycle {cycle_id!r} not found in episode records. "
            "The cycle may not have produced memory records yet.",
            err=True,
        )
        sys.exit(2)

    session_id = ep_row["runtime_session_id"]
    evs = _cycle_events_from_fossic(vault_path, session_id, cycle_id)

    if not evs:
        click.echo(f"No events found in FossicStore for cycle {cycle_id!r}.", err=True)
        sys.exit(2)

    def _pick(etype: str) -> list[dict[str, Any]]:
        return [e for e in evs if e["event_type"] == etype]

    started_evs = _pick("CycleStarted")
    completed_evs = _pick("CycleCompleted")
    signal_evs = _pick("SignalEvaluated")
    clutch_evs = _pick("ClutchDecisionMade")
    step_started = _pick("StepStarted")
    step_executed = _pick("StepExecuted")

    started_p = started_evs[0]["payload"] if started_evs else {}
    completed_p = completed_evs[0]["payload"] if completed_evs else {}

    if output_json:
        click.echo(json.dumps({
            "cycle_id": cycle_id,
            "session_id": session_id,
            "cycle_config": started_p.get("cycle_config"),
            "started_at_ms": started_p.get("started_at"),
            "completed_at_ms": completed_p.get("completed_at"),
            "outcome": completed_p.get("outcome"),
            "total_steps": completed_p.get("total_steps"),
            "signals": [e["payload"] for e in signal_evs],
            "clutch_decisions": [e["payload"] for e in clutch_evs],
            "step_trace": [e["payload"] for e in step_started + step_executed],
        }, indent=2))
        return

    if signals:
        click.echo(f"Signals for cycle {cycle_id}:")
        if not signal_evs:
            click.echo("  (no SignalEvaluated events found)")
        for ev in signal_evs:
            p = ev["payload"]
            name = p.get("signal_name", "?")
            score = p.get("signal_score")
            strength = p.get("signal_strength")
            low_conf = p.get("low_confidence", False)
            score_str = f"{score:.4f}" if score is not None else "—"
            strength_str = f"{strength:.4f}" if strength is not None else "—"
            flags = "  [low-confidence]" if low_conf else ""
            click.echo(f"  {name:<24}  score={score_str}  strength={strength_str}{flags}")
        return

    if clutch:
        click.echo(f"Clutch decisions for cycle {cycle_id}:")
        if not clutch_evs:
            click.echo("  (no ClutchDecisionMade events found)")
        for ev in clutch_evs:
            p = ev["payload"]
            action = p.get("action", "?")
            rule = p.get("rule_matched", "—")
            depth = p.get("cascade_depth", 0)
            escalate = p.get("escalate_to_catalyst", False)
            esc_note = "  [→catalyst]" if escalate else ""
            click.echo(f"  {p.get('step_id', '?'):<14}  {action:<12}  rule={rule}  depth={depth}{esc_note}")
        return

    if steps:
        click.echo(f"Steps for cycle {cycle_id}:")
        step_map: dict[str, dict[str, Any]] = {}
        for ev in step_started:
            sid = ev["payload"].get("step_id", "?")
            step_map[sid] = {"started": ev["payload"]}
        for ev in step_executed:
            sid = ev["payload"].get("step_id", "?")
            step_map.setdefault(sid, {})["executed"] = ev["payload"]
        for step_id_key, parts in sorted(step_map.items()):
            sp = parts.get("started", {})
            ep = parts.get("executed", {})
            name = sp.get("step_name", ep.get("step_name", "?"))
            status = "ok" if ep else "no output"
            tokens = ep.get("output_tokens")
            tok_note = f"  {tokens}tok" if tokens else ""
            click.echo(f"  {step_id_key:<14}  {name:<20}  {status}{tok_note}")
        return

    # ── default summary view ──────────────────────────────────────────────────
    click.echo(f"Cycle {cycle_id}")
    click.echo(f"  Session:      {session_id}")
    click.echo(f"  Config:       {started_p.get('cycle_config', '—')}")
    if completed_p.get("outcome"):
        click.echo(f"  Outcome:      {completed_p['outcome']}")
    if completed_p.get("total_steps"):
        click.echo(f"  Total steps:  {completed_p['total_steps']}")
    click.echo(f"  Events:       {len(evs)} total")
    if signal_evs:
        scores = [e["payload"].get("signal_score") for e in signal_evs if e["payload"].get("signal_score") is not None]
        avg = sum(scores) / len(scores) if scores else None
        avg_str = f"{avg:.4f}" if avg is not None else "—"
        click.echo(f"  Avg signal:   {avg_str}  ({len(signal_evs)} signals evaluated)")
    click.echo(f"\nUse --signals, --clutch, or --steps for detail views.")


# ── inspect memory ────────────────────────────────────────────────────────────


@inspect.group("memory")
def inspect_memory() -> None:
    """Inspect memory records."""


@inspect_memory.command("show")
@click.argument("memory_id")
@click.option("--vault", default=None, help="Vault path.")
@click.option("--history", is_flag=True, default=False, help="Show event history for this record.")
@click.option("--graph", is_flag=True, default=False, help="Show graph neighbors.")
@click.option("--json", "output_json", is_flag=True, default=False)
def memory_show(
    memory_id: str, vault: str | None, history: bool, graph: bool, output_json: bool
) -> None:
    """Show memory record MEMORY_ID."""
    import sys

    vault_path, db_path = _get_db(vault)

    with connect(db_path) as conn:
        rec = conn.execute(
            "SELECT mr.record_id, mr.content, mr.sku_address, mr.lifecycle_state, "
            "       mr.created_at, mr.token_estimate, s.canonical_path "
            "FROM memory_records mr "
            "LEFT JOIN sources s ON mr.source_id = s.source_id "
            "WHERE mr.record_id = ?",
            (memory_id,),
        ).fetchone()

        if rec is None:
            click.echo(f"Memory record {memory_id!r} not found.", err=True)
            sys.exit(2)

        sku_row = conn.execute(
            "SELECT d1, d2, d3, d9, d10, d1_confidence "
            "FROM sku_assignments WHERE record_id = ? "
            "ORDER BY rowid DESC LIMIT 1",
            (memory_id,),
        ).fetchone()

    if history:
        from cerebra.inspector.sqlite_log import SQLiteEventLog
        log = SQLiteEventLog(db_path)
        evs = log.query_by_subject(memory_id)
        if output_json:
            click.echo(json.dumps(evs, indent=2))
            return
        click.echo(f"Event history for {memory_id}  ({len(evs)} events):")
        for ev in evs:
            _render_event_brief(ev)
        return

    if graph:
        graph_path = vault_path / ".cerebra" / "graph.json"
        if not graph_path.exists():
            click.echo("Graph not exported yet. Run `cerebra export graph` first.", err=True)
            sys.exit(2)
        with open(graph_path) as f:
            g = json.load(f)
        node_id = f"record:{memory_id}"
        edges = [e for e in g.get("edges", []) if e.get("source") == node_id or e.get("target") == node_id]
        neighbor_ids = {(e["target"] if e["source"] == node_id else e["source"]) for e in edges}
        if output_json:
            click.echo(json.dumps({"node_id": node_id, "edges": edges}, indent=2))
            return
        click.echo(f"Graph neighbors for {memory_id}  ({len(edges)} edges):")
        for eid in sorted(neighbor_ids):
            relevant = [e for e in edges if e.get("source") == eid or e.get("target") == eid]
            etype = relevant[0].get("edge_type", "?") if relevant else "?"
            click.echo(f"  {eid}  [{etype}]")
        return

    r = dict(rec)
    if output_json:
        obj: dict[str, Any] = {
            "record_id": r["record_id"],
            "sku_address": r.get("sku_address"),
            "lifecycle_state": r.get("lifecycle_state"),
            "source": r.get("canonical_path"),
            "token_estimate": r.get("token_estimate"),
            "created_at": r.get("created_at"),
            "content_preview": (r.get("content") or "")[:200],
        }
        if sku_row:
            obj["sku"] = dict(sku_row)
        click.echo(json.dumps(obj, indent=2))
        return

    click.echo(f"Memory record:  {memory_id}")
    click.echo(f"SKU:            {r.get('sku_address') or '(unclassified)'}")
    click.echo(f"Lifecycle:      {r.get('lifecycle_state', '—')}")
    click.echo(f"Source:         {r.get('canonical_path') or '—'}")
    click.echo(f"Tokens:         {r.get('token_estimate', '—')}")
    click.echo(f"Created:        {_fmt_ts(r.get('created_at'))}")
    if sku_row:
        s = dict(sku_row)
        try:
            from cerebra.cognition.sku_categories import D1Category
            d1_name = D1Category(s["d1"]).name
        except Exception:
            d1_name = str(s.get("d1"))
        click.echo(f"D1:             {d1_name}  (conf={s.get('d1_confidence', 0):.3f})")
    content = (r.get("content") or "")
    preview = content[:200].replace("\n", " ")
    if len(content) > 200:
        preview += "…"
    click.echo(f"\n{preview}")
    click.echo(f"\nUse --history for event trail, --graph for knowledge graph neighbors.")


# ── inspect retrieval ─────────────────────────────────────────────────────────


@inspect.group("retrieval")
def inspect_retrieval() -> None:
    """Inspect retrieval traces."""


@inspect_retrieval.command("show")
@click.argument("retrieval_id")
@click.option("--vault", default=None, help="Vault path.")
@click.option("--path", "show_path", is_flag=True, default=False, help="Show traversal steps.")
@click.option("--scores", is_flag=True, default=False, help="Show all candidate scores.")
@click.option("--json", "output_json", is_flag=True, default=False)
def retrieval_show(
    retrieval_id: str,
    vault: str | None,
    show_path: bool,
    scores: bool,
    output_json: bool,
) -> None:
    """Show retrieval trace RETRIEVAL_ID."""
    import sys

    _, db_path = _get_db(vault)

    with connect(db_path) as conn:
        trace = conn.execute(
            "SELECT * FROM retrieval_traces WHERE trace_id = ?",
            (retrieval_id,),
        ).fetchone()

        if trace is None:
            click.echo(f"Retrieval trace {retrieval_id!r} not found.", err=True)
            sys.exit(2)

        if show_path or output_json:
            steps = conn.execute(
                "SELECT * FROM retrieval_steps WHERE trace_id = ? ORDER BY step_number ASC",
                (retrieval_id,),
            ).fetchall()
        else:
            steps = []

        if scores or output_json:
            candidates = conn.execute(
                "SELECT record_id, step_surfaced, retrieval_path, salience_score, "
                "       selected, rank, exclusion_reason, score_json "
                "FROM retrieval_candidates WHERE trace_id = ? ORDER BY salience_score DESC",
                (retrieval_id,),
            ).fetchall()
        else:
            candidates = []

    t = dict(trace)

    if output_json:
        click.echo(json.dumps({
            "trace": t,
            "steps": [dict(s) for s in steps],
            "candidates": [dict(c) for c in candidates],
        }, indent=2))
        return

    click.echo(f"Retrieval trace:  {retrieval_id}")
    click.echo(f"Query:            {t.get('query', '—')}")
    click.echo(f"Mode:             {t.get('mode', '—')}")
    click.echo(f"Duration:         {t.get('duration_ms', '—')}ms")
    click.echo(f"Candidates:       {t.get('candidate_count', 0)}")
    click.echo(f"Selected:         {t.get('selected_count', 0)}")
    click.echo(f"Abstained:        {'yes' if t.get('abstained') else 'no'}")
    click.echo(f"Started:          {_fmt_ts(t.get('started_at'))}")

    if show_path:
        click.echo(f"\nTraversal path  ({len(steps)} steps):")
        for s in steps:
            step = dict(s)
            skip_note = f"  [skipped: {step.get('skip_reason')}]" if step.get("skipped") else ""
            click.echo(
                f"  {step.get('step_number', '?'):>2}.  {step.get('step_name', '?'):<22}"
                f"  +{step.get('new_candidates', 0)} new  ({step.get('duration_ms', 0)}ms){skip_note}"
            )

    if scores:
        click.echo(f"\nCandidates  ({len(candidates)} total):")
        for c in candidates:
            cand = dict(c)
            sel_mark = "*" if cand.get("selected") else " "
            rank_str = f"#{cand['rank']}" if cand.get("rank") is not None else "  "
            excl = f"  [excl: {cand['exclusion_reason']}]" if cand.get("exclusion_reason") else ""
            click.echo(
                f"  {sel_mark}{rank_str:<4}  {cand['salience_score']:.4f}"
                f"  {cand['record_id']:<22}  {cand.get('retrieval_path', '?')}{excl}"
            )

    if not show_path and not scores:
        click.echo(f"\nUse --path for traversal steps, --scores for candidate list.")


# ── inspect leeway ────────────────────────────────────────────────────────────


@inspect.group("leeway")
def inspect_leeway() -> None:
    """Inspect leeway grants and revocations."""


@inspect_leeway.command("active")
@click.option("--vault", default=None, help="Vault path.")
@click.option("--json", "output_json", is_flag=True, default=False)
def leeway_active(vault: str | None, output_json: bool) -> None:
    """Show recent LeewayGrantApplied events across all sessions."""
    vault_path, _ = _get_db(vault)
    store = _fossic_store_for(vault_path)
    if store is None:
        click.echo("No FossicStore found. Run at least one cognitive cycle first.")
        return

    evs = store.read_events(stream_pattern="cerebra/agent-trace/*", event_type="LeewayGrantApplied")

    if output_json:
        click.echo(json.dumps([e["payload"] for e in evs], indent=2))
        return

    if not evs:
        click.echo("No LeewayGrantApplied events found.")
        return

    click.echo(f"Recent leeway grants  ({len(evs)} total):")
    for ev in evs:
        p = ev["payload"]
        session = p.get("session_id", "?")[:14]
        cycle = p.get("cycle_id", "?")[:14]
        action = p.get("proposed_action", "?")
        decision = p.get("final_decision", "?")
        grants = p.get("grants_applied", [])
        grants_str = ", ".join(grants) if isinstance(grants, list) else str(grants)
        click.echo(f"  [{decision}]  session={session}  cycle={cycle}  action={action}  grants=[{grants_str}]")


@inspect_leeway.command("history")
@click.argument("session_id")
@click.option("--vault", default=None, help="Vault path.")
@click.option("--json", "output_json", is_flag=True, default=False)
def leeway_history(session_id: str, vault: str | None, output_json: bool) -> None:
    """Show all leeway events for SESSION_ID."""
    vault_path, _ = _get_db(vault)
    all_evs = _session_events_from_fossic(vault_path, session_id)
    leeway_types = {
        "LeewayGrantApplied", "LeewayGrantDenied", "LeewayRevocationFired",
        "ConstitutionalBlock", "LeewayRuleLoaded", "LeewayRuleExpired",
    }
    evs = [e for e in all_evs if e["event_type"] in leeway_types]

    if output_json:
        click.echo(json.dumps([{"event_type": e["event_type"], "payload": e["payload"]} for e in evs], indent=2))
        return

    click.echo(f"Leeway events for session {session_id}  ({len(evs)} events):")
    for ev in evs:
        p = ev["payload"]
        etype = ev["event_type"]
        action = p.get("proposed_action") or p.get("rule_id", "?")
        decision = p.get("final_decision", "")
        decision_note = f"  [{decision}]" if decision else ""
        click.echo(f"  {etype:<30}  {action}{decision_note}")


@inspect_leeway.command("revocations")
@click.option("--vault", default=None, help="Vault path.")
@click.option("--json", "output_json", is_flag=True, default=False)
def leeway_revocations(vault: str | None, output_json: bool) -> None:
    """Show all LeewayRevocationFired events."""
    vault_path, _ = _get_db(vault)
    store = _fossic_store_for(vault_path)
    if store is None:
        click.echo("No FossicStore found. Run at least one cognitive cycle first.")
        return

    evs = store.read_events(stream_pattern="cerebra/agent-trace/*", event_type="LeewayRevocationFired")

    if output_json:
        click.echo(json.dumps([e["payload"] for e in evs], indent=2))
        return

    if not evs:
        click.echo("No LeewayRevocationFired events found.")
        return

    click.echo(f"Leeway revocations  ({len(evs)} total):")
    for ev in evs:
        p = ev["payload"]
        session = p.get("session_id", "?")[:14]
        rule = p.get("rule_id", "?")
        reason = p.get("reason", "?")
        click.echo(f"  session={session}  rule={rule}  reason={reason}")


# ── inspect query ─────────────────────────────────────────────────────────────


def _query_inspector_events(
    db_path: Path,
    *,
    event_type: str | None,
    since_ts: int | None,
    cycle_id: str | None,
    extra_filter: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Query inspector_events with optional filters."""
    clauses: list[str] = []
    params: list[Any] = []

    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    if since_ts is not None:
        clauses.append("timestamp >= ?")
        params.append(since_ts)
    if cycle_id:
        clauses.append("cycle_id = ?")
        params.append(cycle_id)
    if extra_filter:
        # Parse "key=value" and apply as json_extract on data_json
        if "=" in extra_filter:
            key, _, value = extra_filter.partition("=")
            clauses.append(f"json_extract(data_json, '$.{key.strip()}') = ?")
            params.append(value.strip())

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT rowid AS _rowid, * FROM inspector_events "
            f"{where} ORDER BY timestamp DESC LIMIT ?",
            params,
        ).fetchall()

    return [dict(r) for r in rows]


@inspect.command("query")
@click.option("--vault", default=None, help="Vault path.")
@click.option("--event-type", "event_type", default=None, help="Filter by event type.")
@click.option(
    "--signal-low", "signal_low", default=None, metavar="SIGNAL",
    help="Signal name to filter low scores (e.g. GROUNDEDNESS). Queries FossicStore.",
)
@click.option(
    "--threshold", type=float, default=0.5, show_default=True,
    help="Score threshold for --signal-low.",
)
@click.option(
    "--severe-misses", "severe_misses", is_flag=True, default=False,
    help="Show PredictionSevereMiss events (FossicStore).",
)
@click.option(
    "--last", "last_window", default=None, metavar="WINDOW",
    help="Time window, e.g. '1h', '24h', '7d'.",
)
@click.option(
    "--cycle", "cycle_id", default=None, metavar="CYCLE_ID",
    help="Filter to a specific cycle.",
)
@click.option(
    "--filter", "extra_filter", default=None, metavar="KEY=VALUE",
    help="Filter on data_json field, e.g. 'action=escalate'.",
)
@click.option(
    "--tail", is_flag=True, default=False,
    help="Tail new events (SQLite inspector_events only).",
)
@click.option("--limit", default=50, show_default=True, help="Max events to return.")
@click.option("--json", "output_json", is_flag=True, default=False)
def inspect_query(
    vault: str | None,
    event_type: str | None,
    signal_low: str | None,
    threshold: float,
    severe_misses: bool,
    last_window: str | None,
    cycle_id: str | None,
    extra_filter: str | None,
    tail: bool,
    limit: int,
    output_json: bool,
) -> None:
    """Flexible event query across the inspector event log.

    \b
    Examples:
      cerebra inspect query --event-type RetrievalAbstained --last 1h
      cerebra inspect query --signal-low GROUNDEDNESS --threshold 0.4
      cerebra inspect query --severe-misses --last 24h
      cerebra inspect query --cycle cyc_abc --filter "action=escalate"
      cerebra inspect query --event-type WorkingMemoryRendered --tail
    """
    vault_path, db_path = _get_db(vault)

    since_ts = None
    window_secs = _parse_last(last_window)
    if window_secs is not None:
        since_ts = int(time.time()) - window_secs

    # ── FossicStore-backed queries ────────────────────────────────────────────
    if signal_low or severe_misses:
        store = _fossic_store_for(vault_path)
        if store is None:
            click.echo("No FossicStore found (no cycles run yet).")
            return

        if signal_low:
            all_evs = store.read_events(
                stream_pattern="cerebra/agent-trace/*",
                event_type="SignalEvaluated",
            )
            matched = [
                e for e in all_evs
                if e["payload"].get("signal_name", "").upper() == signal_low.upper()
                and (e["payload"].get("signal_score") or 1.0) < threshold
            ]
            if cycle_id:
                matched = [e for e in matched if e["payload"].get("cycle_id") == cycle_id]
            if since_ts is not None:
                matched = [
                    e for e in matched
                    if (e["payload"].get("evaluated_at") or 0) >= since_ts * 1000
                ]
            matched = matched[-limit:]
        elif severe_misses:
            all_evs = store.read_events(
                stream_pattern="cerebra/agent-trace/*",
                event_type="PredictionSevereMiss",
            )
            matched = all_evs
            if cycle_id:
                matched = [e for e in matched if e["payload"].get("cycle_id") == cycle_id]
            if since_ts is not None:
                matched = [
                    e for e in matched
                    if (e["payload"].get("recorded_at") or 0) >= since_ts * 1000
                ]
            matched = matched[-limit:]
        else:
            matched = []

        if output_json:
            click.echo(json.dumps(
                [{"event_type": e["event_type"], **e["payload"]} for e in matched], indent=2
            ))
            return

        if not matched:
            click.echo("No matching events found.")
            return

        click.echo(f"Results  ({len(matched)} events):")
        for ev in matched:
            p = ev["payload"]
            etype = ev["event_type"]
            if etype == "SignalEvaluated":
                score = p.get("signal_score")
                name = p.get("signal_name", "?")
                cycle = p.get("cycle_id", "?")[:12]
                click.echo(
                    f"  {name:<24}  score={score:.4f}"
                    f"  cycle={cycle}  step={p.get('step_id', '?')}"
                )
            elif etype == "PredictionSevereMiss":
                err = p.get("prediction_error", "?")
                cycle = p.get("cycle_id", "?")[:12]
                click.echo(
                    f"  PredictionSevereMiss  error={err:.4f}"
                    f"  expected={p.get('expected', '?'):.4f}"
                    f"  actual={p.get('actual', '?'):.4f}  cycle={cycle}"
                )
        return

    # ── SQLite inspector_events query ─────────────────────────────────────────
    rows = _query_inspector_events(
        db_path,
        event_type=event_type,
        since_ts=since_ts,
        cycle_id=cycle_id,
        extra_filter=extra_filter,
        limit=limit,
    )

    if tail:
        # Initial display + polling loop
        if output_json:
            for r in rows:
                click.echo(json.dumps({k: v for k, v in r.items() if k != "_rowid"}))
        else:
            click.echo(f"Showing {len(rows)} recent event(s). Tailing for new events... (Ctrl+C to stop)")
            for r in reversed(rows):
                _render_event_brief(r)

        last_rowid = max((r.get("_rowid", 0) for r in rows), default=0)

        try:
            while True:
                time.sleep(0.5)
                tail_clauses: list[str] = ["rowid > ?"]
                tail_params: list[Any] = [last_rowid]
                if event_type:
                    tail_clauses.append("event_type = ?")
                    tail_params.append(event_type)
                if cycle_id:
                    tail_clauses.append("cycle_id = ?")
                    tail_params.append(cycle_id)
                if extra_filter and "=" in extra_filter:
                    key, _, value = extra_filter.partition("=")
                    tail_clauses.append(f"json_extract(data_json, '$.{key.strip()}') = ?")
                    tail_params.append(value.strip())
                tail_params.append(200)
                with connect(db_path) as conn:
                    new_rows = conn.execute(
                        f"SELECT rowid AS _rowid, * FROM inspector_events "
                        f"WHERE {' AND '.join(tail_clauses)} "
                        f"ORDER BY rowid ASC LIMIT ?",
                        tail_params,
                    ).fetchall()
                for new_r in [dict(nr) for nr in new_rows]:
                    if output_json:
                        click.echo(json.dumps({k: v for k, v in new_r.items() if k != "_rowid"}))
                    else:
                        _render_event_brief(new_r)
                    last_rowid = max(last_rowid, new_r.get("_rowid", last_rowid))
        except KeyboardInterrupt:
            if not output_json:
                click.echo("\nTail stopped.")
        return

    if output_json:
        for r in rows:
            click.echo(json.dumps({k: v for k, v in r.items() if k != "_rowid"}))
        return

    if not rows:
        click.echo("No matching events found.")
        return

    click.echo(f"Results  ({len(rows)} events, newest first):")
    for r in rows:
        _render_event_brief(r)
