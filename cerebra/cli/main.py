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


# ── classify ──────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--vault", default=None, help="Vault path (overrides env + config).")
@click.option("--batch-size", default=50, show_default=True, help="Records per commit batch.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Count records needing SKU, write nothing."
)
@click.option("--json", "output_json", is_flag=True, default=False, help="Output report as JSON.")
def classify(
    vault: str | None,
    batch_size: int,
    dry_run: bool,
    output_json: bool,
) -> None:
    """Assign SKU addresses to all unclassified memory records."""
    import json as json_mod

    from cerebra.cognition.llm_adapter import OllamaDirectAdapter
    from cerebra.cognition.sku_classifier import SKUClassifier
    from cerebra.inspector.ndjson_log import NDJSONEventLog
    from cerebra.inspector.sqlite_log import SQLiteEventLog
    from cerebra.storage.migrations import run_migrations
    from cerebra.storage.sqlite_store import SQLiteStore

    vault_path = _get_vault(vault)
    db_path = vault_path / "data" / "cerebra.db"
    events_log = vault_path / "events" / "classify.ndjson"

    run_migrations(db_path)
    store = SQLiteStore(db_path)
    event_log = SQLiteEventLog(db_path)
    ndjson = NDJSONEventLog(events_log)

    adapter = OllamaDirectAdapter()
    if not dry_run and not adapter.health_check():
        raise click.ClickException(
            "Ollama unreachable. Start the AI stack:\n"
            "  cd ~/Projects/ai-stack && docker compose up -d"
        )

    classifier = SKUClassifier(
        store=store,
        event_log=event_log,
        ndjson=ndjson,
        adapter=adapter,
    )

    try:
        report = classifier.backfill_null_records(batch_size=batch_size, dry_run=dry_run)
    except Exception as e:
        raise click.ClickException(f"Classify failed: {e}") from e

    if output_json:
        click.echo(json_mod.dumps(report.as_dict(), indent=2))
        return

    prefix = "[dry-run] " if dry_run else ""
    click.echo(f"{prefix}Classify complete:")
    click.echo(f"  Found:          {report.records_found}")
    click.echo(f"  Classified:     {report.classified}")
    click.echo(f"  Skipped:        {report.skipped}")
    click.echo(f"  Failed:         {report.failed}")
    click.echo(f"  Low confidence: {report.low_confidence}")
    click.echo(f"  Elapsed:        {report.elapsed_ms}ms")


# ── search ────────────────────────────────────────────────────────────────────


def _d1_label(query_d1: int | None) -> str:
    """Return a human-readable D1 label, e.g. 'DESIGN (0x5)' or 'none'."""
    if query_d1 is None:
        return "none"
    try:
        from cerebra.cognition.sku_categories import D1Category
        return f"{D1Category(query_d1).name} (0x{query_d1:x})"
    except (ValueError, ImportError):
        return f"0x{query_d1:x}"


def _truncate(s: str, n: int) -> str:
    return s[:n] + "…" if len(s) > n else s


def _render_text(
    scored: list,
    plan,
    above_floor: int,
    duration_ms: int,
    limit: int,
    explain: bool,
    floor: float,
) -> None:
    """Render plain-text search output matching §12 design."""
    visible = scored[:limit]

    click.echo(
        f'\nQuery: "{plan.raw_query}"  '
        f"Mode: {plan.mode}  "
        f"D1: {_d1_label(plan.query_d1)}"
    )
    click.echo(
        f"Candidates: {len(scored)}  "
        f"Above floor ({floor}): {above_floor}  "
        f"Duration: {duration_ms}ms"
    )

    if plan.staleness_warnings:
        for w in plan.staleness_warnings:
            click.echo(f"  [stale] {w}", err=True)

    if not visible:
        click.echo(
            f"\nNo results above salience floor {floor}. "
            "Try a broader query or lower --floor.",
            err=True,
        )
        return

    # Table header
    click.echo(f"\n{'Rank':>4}  {'Score':>6}  {'Source':<45}  Excerpt")
    click.echo(f"{'----':>4}  {'------':>6}  {'-' * 45}  -------")

    for c in visible:
        src = _truncate(c.source_path, 45)
        excerpt = _truncate(c.content_excerpt.replace("\n", " "), 60)
        click.echo(f"{c.rank:>4}  {c.score.composite:>6.2f}  {src:<45}  {excerpt}")

    # Retrieval paths
    click.echo("\nRetrieval paths:")
    for c in visible:
        click.echo(f"  #{c.rank}: {c.retrieval_path}")

    # Per-component breakdown (--explain)
    if explain:
        click.echo("\nScore breakdown:")
        for c in visible:
            parts = "  ".join(
                f"{row['component']}={row['value']:.3f}×{row['weight']:.2f}={row['contribution']:.3f}"
                for row in c.score.explain()
            )
            click.echo(f"  #{c.rank}: {parts}")


def _render_json(scored: list, limit: int, explain: bool) -> None:
    """Render JSON (ndjson) output — one candidate per line."""
    for c in scored[:limit]:
        obj: dict = {
            "rank": c.rank,
            "score": round(c.score.composite, 6),
            "record_id": c.record_id,
            "source_path": c.source_path,
            "retrieval_path": c.retrieval_path,
            "sku_address": c.sku_address,
            "created_at": c.created_at,
            "content_excerpt": c.content_excerpt,
            "components": {k: round(v, 6) for k, v in c.score.components.items()},
        }
        if explain:
            obj["explain"] = c.score.explain()
        click.echo(json.dumps(obj))


@cli.command()
@click.argument("query")
@click.option("--vault", default=None, help="Vault path (overrides env + config).")
@click.option(
    "--limit", default=10, show_default=True,
    help="Maximum results to show (1–200).",
)
@click.option(
    "--floor", "relevance_floor", default=0.35, show_default=True,
    help="Minimum salience score to include in results.",
)
@click.option(
    "--format", "output_format",
    type=click.Choice(["text", "json"]), default="text", show_default=True,
    help="Output format.",
)
@click.option("--explain", is_flag=True, default=False, help="Show per-component score breakdown.")
def search(
    query: str,
    vault: str | None,
    limit: int,
    relevance_floor: float,
    output_format: str,
    explain: bool,
) -> None:
    """Search the vault for memory records matching QUERY."""
    import sys
    import time

    from cerebra.inspector.event import make_event
    from cerebra.inspector.sqlite_log import SQLiteEventLog
    from cerebra.retrieval.planner import query_plan
    from cerebra.retrieval.scorer import score_candidates
    from cerebra.retrieval.trace import TraceData, write_trace
    from cerebra.retrieval.traversal import run_traversal
    from cerebra.storage.migrations import run_migrations

    limit = max(1, min(limit, 200))

    try:
        vault_path = _get_vault(vault)
    except Exception as e:
        msg = e.format_message() if isinstance(e, click.ClickException) else str(e)
        click.echo(f"Error: {msg}", err=True)
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

    try:
        t_start = time.monotonic_ns()
        started_at = int(time.time())
        event_log = SQLiteEventLog(db_path)
        plan = query_plan(query, db_path, max_candidates=200, event_log=event_log)
        raw = run_traversal(plan, db_path, event_log=event_log)
        scored_all = score_candidates(raw, plan, db_path, event_log=event_log)
        finished_at = int(time.time())
        duration_ms = max(0, (time.monotonic_ns() - t_start) // 1_000_000)
    except Exception as e:
        click.echo(f"Error: retrieval failed: {e}", err=True)
        sys.exit(2)

    # ── Write retrieval trace ─────────────────────────────────────────────────
    try:
        step_events = [
            json.loads(e["data_json"])
            for e in event_log.query_by_subject(plan.trace_id, "TraversalStepCompleted")
        ]
        trace_data = TraceData(
            plan=plan,
            scored_all=scored_all,
            floor=relevance_floor,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            step_events=step_events,
        )
        write_trace(trace_data, db_path, event_log=event_log)
    except Exception as e:
        click.echo(f"Error: trace write failed: {e}", err=True)
        sys.exit(2)

    # Lattice sibling dedup: collapse sibling groups to winner (after trace write)
    from cerebra.retrieval.lattice_dedup import dedup_siblings
    scored_all = dedup_siblings(scored_all, plan.query_d1, db_path, plan.trace_id, event_log)

    best_score = max((c.score.composite for c in scored_all), default=0.0)
    if best_score < relevance_floor:
        event_log.write(make_event(
            event_type="RetrievalAbstained",
            actor="retrieval",
            summary=f"Abstained: best score {best_score:.4f} < floor {relevance_floor}",
            data={
                "trace_id": plan.trace_id,
                "query": plan.raw_query,
                "mode": plan.mode,
                "query_sku_d1": plan.query_d1,
                "candidate_count": len(scored_all),
                "best_score_seen": round(best_score, 6),
                "floor": relevance_floor,
            },
            subject_id=plan.trace_id,
        ))
        click.echo(
            f"No relevant results above floor {relevance_floor:.2f} "
            f"(best score: {best_score:.2f})",
            err=True,
        )
        sys.exit(1)

    above_floor = [c for c in scored_all if c.score.composite >= relevance_floor]
    above_count = len(above_floor)

    if output_format == "json":
        _render_json(above_floor, limit, explain)
        return

    _render_text(above_floor, plan, above_count, duration_ms, limit, explain, relevance_floor)


# ── reindex ───────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--vault", default=None, help="Vault path (overrides env + config).")
@click.option("--lexical", "do_lexical", is_flag=True, default=False, help="Rebuild the FTS5 lexical index.")
@click.option("--vector", "do_vector", is_flag=True, default=False, help="Rebuild the vector (embedding) index.")
@click.pass_context
def reindex(ctx: click.Context, vault: str | None, do_lexical: bool, do_vector: bool) -> None:
    """Rebuild search indexes for the vault.

    \b
    --lexical   Rebuild the FTS5 full-text index from all active records.
    --vector    Not yet implemented (use `cerebra reembed` when available).

    Run without flags to see this help.
    """
    import sys
    import time

    from cerebra.storage.lexical import build_fts_index
    from cerebra.storage.migrations import run_migrations

    if not do_lexical and not do_vector:
        click.echo(ctx.get_help())
        return

    if do_vector:
        click.echo(
            "Vector reindexing is not yet implemented. "
            "Use `cerebra reembed` when available (Phase 5).",
            err=True,
        )
        if not do_lexical:
            sys.exit(2)

    if do_lexical:
        vault_path = _get_vault(vault)
        db_path = vault_path / "data" / "cerebra.db"
        if not db_path.exists():
            click.echo(f"Error: vault database not found at {db_path}", err=True)
            sys.exit(2)

        try:
            run_migrations(db_path)

            from cerebra.storage.db import connect
            with connect(db_path) as conn:
                total = conn.execute(
                    "SELECT COUNT(*) FROM memory_records WHERE lifecycle_state = 'active'"
                ).fetchone()[0]

            click.echo(f"Rebuilding FTS5 lexical index for {total} active records...")
            t0 = time.monotonic()
            count = build_fts_index(db_path)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            click.echo(f"Done. {count} records indexed in {elapsed_ms}ms.")
        except Exception as e:
            click.echo(f"Error: lexical reindex failed: {e}", err=True)
            sys.exit(2)


# ── context ───────────────────────────────────────────────────────────────────


@cli.command()
@click.argument("query")
@click.option("--vault", default=None, help="Vault path (overrides env + config).")
@click.option(
    "--limit", default=10, show_default=True,
    help="Maximum records in selected_memory (1–200).",
)
@click.option(
    "--floor", "relevance_floor", default=0.35, show_default=True,
    help="Minimum salience score to include in selected_memory.",
)
@click.option(
    "--format", "output_format",
    type=click.Choice(["text", "json"]), default="text", show_default=True,
    help="Output format.",
)
@click.option(
    "--out", "out_file", default=None,
    help="Write JSON packet to FILE instead of stdout (implies --format json).",
)
@click.option(
    "--no-promote", "no_promote", is_flag=True, default=False,
    help="Skip T1 auto-promotion into working memory. Retrieval only.",
)
def context(
    query: str,
    vault: str | None,
    limit: int,
    relevance_floor: float,
    output_format: str,
    out_file: str | None,
    no_promote: bool,
) -> None:
    """Produce a ContextPacket for QUERY and render it for downstream use."""
    import sys
    import time

    from cerebra.inspector.event import make_event
    from cerebra.inspector.sqlite_log import SQLiteEventLog
    from cerebra.retrieval.context_packet import (
        build_abstained_packet,
        build_context_packet,
        render_text,
    )
    from cerebra.retrieval.planner import query_plan
    from cerebra.retrieval.scorer import score_candidates
    from cerebra.retrieval.trace import TraceData, write_trace
    from cerebra.retrieval.traversal import run_traversal
    from cerebra.storage.migrations import run_migrations

    limit = max(1, min(limit, 200))
    use_json = output_format == "json" or out_file is not None

    try:
        vault_path = _get_vault(vault)
    except Exception as e:
        msg = e.format_message() if isinstance(e, click.ClickException) else str(e)
        click.echo(f"Error: {msg}", err=True)
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

    try:
        t_start = time.monotonic_ns()
        started_at = int(time.time())
        event_log = SQLiteEventLog(db_path)
        plan = query_plan(query, db_path, max_candidates=200, event_log=event_log)
        raw = run_traversal(plan, db_path, event_log=event_log)
        scored_all = score_candidates(raw, plan, db_path, event_log=event_log)
        finished_at = int(time.time())
        duration_ms = max(0, (time.monotonic_ns() - t_start) // 1_000_000)
    except Exception as e:
        click.echo(f"Error: retrieval failed: {e}", err=True)
        sys.exit(2)

    try:
        step_events = [
            json.loads(e["data_json"])
            for e in event_log.query_by_subject(plan.trace_id, "TraversalStepCompleted")
        ]
        trace_data = TraceData(
            plan=plan,
            scored_all=scored_all,
            floor=relevance_floor,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            step_events=step_events,
        )
        write_trace(trace_data, db_path, event_log=event_log)
    except Exception as e:
        click.echo(f"Error: trace write failed: {e}", err=True)
        sys.exit(2)

    # Lattice sibling dedup: collapse sibling groups to winner (after trace write)
    from cerebra.retrieval.lattice_dedup import dedup_siblings
    scored_all = dedup_siblings(scored_all, plan.query_d1, db_path, plan.trace_id, event_log)

    best_score = max((c.score.composite for c in scored_all), default=0.0)
    is_abstained = best_score < relevance_floor

    try:
        if is_abstained:
            event_log.write(make_event(
                event_type="RetrievalAbstained",
                actor="retrieval",
                summary=f"Abstained: best score {best_score:.4f} < floor {relevance_floor}",
                data={
                    "trace_id": plan.trace_id,
                    "query": plan.raw_query,
                    "mode": plan.mode,
                    "query_sku_d1": plan.query_d1,
                    "candidate_count": len(scored_all),
                    "best_score_seen": round(best_score, 6),
                    "floor": relevance_floor,
                },
                subject_id=plan.trace_id,
            ))
            packet = build_abstained_packet(trace_data, best_score, event_log=event_log)
        else:
            above_floor = [c for c in scored_all if c.score.composite >= relevance_floor]
            packet = build_context_packet(
                trace_data, above_floor, db_path, limit=limit, event_log=event_log
            )
    except Exception as e:
        click.echo(f"Error: context packet build failed: {e}", err=True)
        sys.exit(2)

    # T1 auto-promotion (§4 D3): promote selected_memory into truth tower.
    # Lockfile is acquired only for the write phase, not the retrieval phase.
    tower_field: dict | None = None
    if not is_abstained and not no_promote and packet.selected_memory:
        try:
            from cerebra.cli.lockfile import vault_lock
            from cerebra.cognition.truth_tower import TruthTower
            from cerebra.cognition.working_memory import (
                get_active_session,
                new_session as _new_session,
            )
            with vault_lock(vault_path):
                session_id = get_active_session(db_path, str(vault_path))
                if session_id is None:
                    session_id = _new_session(db_path, str(vault_path), event_log)
                tower = TruthTower(db_path, session_id)
                tower.promote_to_t1(
                    packet.selected_memory,
                    packet.retrieval_trace_id,
                    event_log,
                )
                tower_field = tower.to_tower_field(event_log)
        except Exception as e:
            click.echo(f"Warning: T1 promotion failed: {e}", err=True)
    else:
        # Read-only: attach pre-existing tower state if a session is active.
        try:
            from cerebra.cognition.truth_tower import TruthTower
            from cerebra.cognition.working_memory import get_active_session
            session_id = get_active_session(db_path, str(vault_path))
            if session_id:
                tower_field = TruthTower(db_path, session_id).to_tower_field()
        except Exception:
            pass

    packet.truth_tower = tower_field

    if out_file is not None:
        try:
            out_path = Path(out_file)
            out_path.write_text(json.dumps(packet.to_dict(), indent=2))
            click.echo(f"Packet written to {out_path}")
        except Exception as e:
            click.echo(f"Error: could not write output file: {e}", err=True)
            sys.exit(2)
        if is_abstained:
            sys.exit(1)
        return

    if use_json:
        click.echo(json.dumps(packet.to_dict(), indent=2))
    else:
        click.echo(render_text(packet, limit=limit))

    if is_abstained:
        sys.exit(1)


# ── session ───────────────────────────────────────────────────────────────────


@cli.group()
def session() -> None:
    """Manage the active working memory session for a vault."""


@session.command("show")
@click.option("--vault", default=None, help="Vault path (overrides env + config).")
@click.option(
    "--format", "output_format",
    type=click.Choice(["text", "json"]), default="text", show_default=True,
    help="Output format.",
)
def session_show(vault: str | None, output_format: str) -> None:
    """Display the current session and working memory state."""
    import sys
    import time

    from cerebra.cognition.working_memory import (
        count_tower_items,
        count_wm_items,
        get_active_session,
        get_session_row,
    )
    from cerebra.storage.migrations import run_migrations

    try:
        vault_path = _get_vault(vault)
    except Exception as e:
        msg = e.format_message() if isinstance(e, click.ClickException) else str(e)
        click.echo(f"Error: {msg}", err=True)
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

    session_id = get_active_session(db_path, str(vault_path))
    if session_id is None:
        if output_format == "json":
            click.echo(json.dumps({"active_session": None}))
        else:
            click.echo("No active session for this vault.")
        return

    row = get_session_row(db_path, session_id)
    if row is None:
        click.echo("Error: session record missing.", err=True)
        sys.exit(2)

    wm_counts = count_wm_items(db_path, session_id)
    tower_counts = count_tower_items(db_path, session_id)
    wm_total = sum(wm_counts.values())
    t1 = tower_counts.get(1, 0)
    t2 = tower_counts.get(2, 0)

    if output_format == "json":
        click.echo(json.dumps({
            "session_id": session_id,
            "vault_path": row["vault_path"],
            "status": row["status"],
            "started_at": row["started_at"],
            "last_active_at": row["last_active_at"],
            "wm_item_count": wm_total,
            "wm_by_slot": wm_counts,
            "t1_item_count": t1,
            "t2_item_count": t2,
        }, indent=2))
        return

    started = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(row["started_at"]))
    last_active = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(row["last_active_at"]))
    slot_detail = ", ".join(f"{k}: {v}" for k, v in sorted(wm_counts.items())) if wm_counts else "empty"

    click.echo(f"Session:      {session_id}")
    click.echo(f"Vault:        {row['vault_path']}")
    click.echo(f"Status:       {row['status']}")
    click.echo(f"Started:      {started}")
    click.echo(f"Last active:  {last_active}")
    click.echo(f"Working memory: {wm_total} items ({slot_detail})")
    click.echo(f"Tower:        T1: {t1}, T2: {t2}")


@session.command("reset")
@click.option("--vault", default=None, help="Vault path (overrides env + config).")
def session_reset(vault: str | None) -> None:
    """Close the current session and start a new one."""
    import sys

    from cerebra.cli.lockfile import vault_lock
    from cerebra.cognition.working_memory import (
        get_active_session,
        new_session,
    )
    from cerebra.inspector.sqlite_log import SQLiteEventLog
    from cerebra.storage.migrations import run_migrations

    try:
        vault_path = _get_vault(vault)
    except Exception as e:
        msg = e.format_message() if isinstance(e, click.ClickException) else str(e)
        click.echo(f"Error: {msg}", err=True)
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

    with vault_lock(vault_path):
        event_log = SQLiteEventLog(db_path)
        old_id = get_active_session(db_path, str(vault_path))
        new_id = new_session(db_path, str(vault_path), event_log)

    if old_id:
        click.echo(f"Session {old_id} closed. New session: {new_id}")
    else:
        click.echo(f"No previous session. New session: {new_id}")


# ── memory ────────────────────────────────────────────────────────────────────


@cli.group()
def memory() -> None:
    """Inspect and modify the working memory for the active vault session."""


def _memory_vault_db(vault_flag: str | None) -> tuple[Path, Path]:
    """Resolve vault and return (vault_path, db_path); exits 2 on any error."""
    import sys

    from cerebra.storage.migrations import run_migrations

    try:
        vault_path = _get_vault(vault_flag)
    except Exception as e:
        msg = e.format_message() if isinstance(e, click.ClickException) else str(e)
        click.echo(f"Error: {msg}", err=True)
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


@memory.command("status")
@click.option("--vault", default=None, help="Vault path (overrides env + config).")
@click.option(
    "--format", "output_format",
    type=click.Choice(["text", "json"]), default="text", show_default=True,
    help="Output format.",
)
def memory_status(vault: str | None, output_format: str) -> None:
    """Show the contents of the active working memory session."""
    import sys

    from cerebra.cognition._constants import SLOT_CAPACITIES
    from cerebra.cognition.truth_tower import TruthTower
    from cerebra.cognition.working_memory import (
        WorkingMemory,
        get_active_session,
    )
    from cerebra.inspector.event import make_event
    from cerebra.inspector.sqlite_log import SQLiteEventLog
    from cerebra.storage.db import connect

    vault_path, db_path = _memory_vault_db(vault)
    session_id = get_active_session(db_path, str(vault_path))

    if session_id is None:
        if output_format == "json":
            click.echo(json.dumps({"active_session": None}))
        else:
            click.echo("No active session for this vault.")
        return

    wm = WorkingMemory(db_path, session_id)
    tower = TruthTower(db_path, session_id)
    event_log = SQLiteEventLog(db_path)

    if output_format == "json":
        d = wm.to_dict()
        d["vault_path"] = str(vault_path)
        tower_field = tower.to_tower_field()
        d["truth_tower"] = tower_field if tower_field is not None else {
            "t1_items": [], "t2_items": [],
            "t1_count": 0, "t2_count": 0, "stale_count": 0,
        }
        click.echo(json.dumps(d, indent=2))
        event_log.write(make_event(
            "WorkingMemoryRendered",
            actor="cli",
            summary=f"status (json) session={session_id}",
            data={"session_id": session_id, "format": "json",
                  "total_items": d["total_item_count"]},
            session_id=session_id,
        ))
        return

    # Text mode: load items with tower-citation status in one query
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT i.item_id, i.slot_type, i.content_summary, i.salience_score, "
            "       i.is_pinned, i.promoted_at, "
            "       CASE WHEN t.wm_item_id IS NOT NULL THEN 1 ELSE 0 END AS is_tower_cited "
            "FROM working_memory_items i "
            "LEFT JOIN (SELECT DISTINCT wm_item_id FROM truth_tower_items "
            "           WHERE evicted_at IS NULL) t "
            "  ON i.item_id = t.wm_item_id "
            "WHERE i.session_id = ? AND i.evicted_at IS NULL "
            "ORDER BY i.slot_type, i.promoted_at ASC",
            (session_id,),
        ).fetchall()
    finally:
        conn.close()

    # Build per-slot dict
    by_slot: dict[str, list[dict]] = {s: [] for s in SLOT_CAPACITIES}
    for r in rows:
        by_slot[r["slot_type"]].append({
            "item_id": r["item_id"],
            "content_summary": r["content_summary"],
            "salience_score": r["salience_score"],
            "is_pinned": bool(r["is_pinned"]),
            "is_tower_cited": bool(r["is_tower_cited"]),
        })

    total = sum(len(v) for v in by_slot.values())
    click.echo(f"Working Memory  session: {session_id}")
    click.echo(f"Vault: {vault_path}")
    click.echo(f"Total: {total} items")

    for slot_type in sorted(SLOT_CAPACITIES):
        items = by_slot[slot_type]
        cap = SLOT_CAPACITIES[slot_type]
        if not items:
            click.echo(f"\n[{slot_type}]  0/{cap}")
            continue
        click.echo(f"\n[{slot_type}]  {len(items)}/{cap}")
        for item in items:
            markers = ""
            if item["is_pinned"]:
                markers += "  [pinned]"
            if item["is_tower_cited"]:
                markers += "  ^T1"
            summary = item["content_summary"]
            if len(summary) > 120:
                summary = summary[:120] + "…"
            click.echo(
                f"  {item['item_id']}  score: {item['salience_score']:.4f}{markers}"
            )
            click.echo(f"    {summary}")

    # Tower section
    t1_items = tower.load_tier(1)
    t2_items = tower.load_tier(2)
    if not t1_items and not t2_items:
        click.echo("\nTruth Tower: empty")
    else:
        stale_count = sum(1 for i in t2_items if i.is_stale)
        click.echo(
            f"\nTruth Tower  ({len(t1_items)} T1, {len(t2_items)} T2, {stale_count} stale):\n"
        )
        t2_by_t1: dict[str, list] = {}
        for t2 in t2_items:
            if t2.t1_citation_id:
                t2_by_t1.setdefault(t2.t1_citation_id, []).append(t2)

        active_t1_ids: set[str] = set()
        for idx, t1 in enumerate(t1_items, start=1):
            active_t1_ids.add(t1.tower_item_id)
            pin_mark = "  [pinned]" if t1.is_pinned else ""
            summary = t1.content_summary
            if len(summary) > 100:
                summary = summary[:100] + "…"
            click.echo(
                f"  T1 [{idx}]  {t1.tower_item_id}  score: {t1.salience_score:.4f}{pin_mark}"
            )
            click.echo(f"    {summary}")
            for t2_idx, t2 in enumerate(t2_by_t1.get(t1.tower_item_id, []), start=1):
                stale_mark = "[stale] " if t2.is_stale else ""
                pin_mark_t2 = "  [pinned]" if t2.is_pinned else ""
                t2_summary = t2.content_summary
                if len(t2_summary) > 100:
                    t2_summary = t2_summary[:100] + "…"
                click.echo(
                    f"    T2 [{t2_idx}] ^T1[{idx}]{pin_mark_t2}  {stale_mark}score: {t2.salience_score:.4f}"
                )
                click.echo(f"      {t2_summary}")

        # Show stale T2 items whose T1 anchor has been evicted
        orphaned_t2 = [t2 for t2 in t2_items if t2.t1_citation_id not in active_t1_ids]
        if orphaned_t2:
            click.echo("  [stale, T1 evicted]:")
            for t2_idx, t2 in enumerate(orphaned_t2, start=1):
                stale_mark = "[stale] " if t2.is_stale else ""
                pin_mark_t2 = "  [pinned]" if t2.is_pinned else ""
                t2_summary = t2.content_summary
                if len(t2_summary) > 100:
                    t2_summary = t2_summary[:100] + "…"
                click.echo(
                    f"    T2 [{t2_idx}]{pin_mark_t2}  {stale_mark}score: {t2.salience_score:.4f}"
                )
                click.echo(f"      {t2_summary}")

    event_log.write(make_event(
        "WorkingMemoryRendered",
        actor="cli",
        summary=f"status (text) session={session_id}",
        data={"session_id": session_id, "format": "text", "total_items": total},
        session_id=session_id,
    ))


@memory.command("promote")
@click.argument("record_id", required=False)
@click.option("--vault", default=None, help="Vault path (overrides env + config).")
@click.option("--slot", "slot_type", default=None, help="Slot to promote into.")
@click.option("--text", "free_text", default=None, help="Synthetic item content (no record_id).")
@click.option("--pin", is_flag=True, default=False, help="Pin item (non-evictable).")
@click.option("--salience", "salience_score", type=float, default=None,
              help="Salience override (0.0–1.0).")
@click.option("--tier", type=click.Choice(["1", "2"]), default=None,
              help="Tower tier for truth tower promotion (2 = T2, requires --cite).")
@click.option("--cite", "cite_id", default=None,
              help="T1 tower_item_id to cite (required with --tier 2).")
def memory_promote(
    record_id: str | None,
    vault: str | None,
    slot_type: str | None,
    free_text: str | None,
    pin: bool,
    salience_score: float | None,
    tier: str | None,
    cite_id: str | None,
) -> None:
    """Promote a record or synthetic item into working memory."""
    import sys

    from cerebra.cli.lockfile import vault_lock
    from cerebra.cognition._constants import SLOT_CAPACITIES
    from cerebra.cognition.working_memory import (
        WorkingMemory,
        WorkingMemoryItem,
        get_active_session,
        new_session,
    )
    from cerebra.inspector.sqlite_log import SQLiteEventLog
    from cerebra.storage.db import connect

    if tier == "1":
        click.echo("Error: T1 tower promotion not yet implemented.", err=True)
        sys.exit(2)

    # ── T2 promotion path ─────────────────────────────────────────────────────
    if tier == "2":
        if cite_id is None:
            click.echo("Error: --cite is required with --tier 2.", err=True)
            sys.exit(2)
        if record_id is None:
            click.echo("Error: provide record_id or wm_item_id for --tier 2.", err=True)
            sys.exit(2)
        positional = record_id
        if not (positional.startswith("wmi_") or positional.startswith("rec_")):
            click.echo(
                f"Error: expected 'rec_<id>' or 'wmi_<id>'; got {positional!r}.",
                err=True,
            )
            sys.exit(2)

        vault_path, db_path = _memory_vault_db(vault)

        # Resolve session and WM item (read-only, pre-validation before acquiring lock)
        session_id = get_active_session(db_path, str(vault_path))
        if session_id is None:
            click.echo(
                f"Error: Working memory item {positional!r} not found in current session "
                "(no active session).",
                err=True,
            )
            sys.exit(2)

        conn = connect(db_path)
        try:
            _wm_select = (
                "SELECT item_id, session_id, slot_type, record_id, content_summary, "
                "       salience_score, is_pinned, promoted_at, evicted_at "
                "FROM working_memory_items "
            )
            if positional.startswith("wmi_"):
                wm_row = conn.execute(
                    _wm_select + "WHERE item_id = ? AND session_id = ?",
                    (positional, session_id),
                ).fetchone()
            else:
                wm_row = conn.execute(
                    _wm_select + "WHERE record_id = ? AND session_id = ?",
                    (positional, session_id),
                ).fetchone()
        finally:
            conn.close()

        if wm_row is None:
            click.echo(
                f"Error: Working memory item {positional!r} not found in current session.",
                err=True,
            )
            sys.exit(2)
        if wm_row["evicted_at"] is not None:
            click.echo(
                f"Error: Working memory item {wm_row['item_id']!r} has been evicted.",
                err=True,
            )
            sys.exit(2)

        wm_item = WorkingMemoryItem(
            item_id=wm_row["item_id"],
            session_id=wm_row["session_id"],
            slot_type=wm_row["slot_type"],
            record_id=wm_row["record_id"],
            content_summary=wm_row["content_summary"],
            salience_score=wm_row["salience_score"],
            is_pinned=bool(wm_row["is_pinned"]),
            promoted_at=wm_row["promoted_at"],
            evicted_at=wm_row["evicted_at"],
        )

        from cerebra.cognition.truth_tower import TowerPromotionError, TruthTower

        with vault_lock(vault_path):
            event_log = SQLiteEventLog(db_path)
            tower = TruthTower(db_path, session_id)
            try:
                t2_item = tower.promote_to_t2(
                    wm_item, cite_id, is_pinned=pin, event_log=event_log
                )
            except TowerPromotionError as e:
                click.echo(f"Error: {e}", err=True)
                sys.exit(2)

        pin_note = "yes" if t2_item.is_pinned else "no"
        click.echo(f"Promoted to T2: {t2_item.tower_item_id}")
        click.echo(f"  Citing T1: {cite_id}")
        click.echo(f"  Session:   {session_id}")
        click.echo(f"  Pinned:    {pin_note}")
        return

    # ── Working memory promote path (tier=None) ───────────────────────────────

    # Validate mutual exclusivity of record_id vs --text
    if free_text is not None and record_id is not None:
        click.echo("Error: --text and record_id are mutually exclusive.", err=True)
        sys.exit(2)
    if free_text is None and record_id is None:
        click.echo("Error: provide either record_id or --text.", err=True)
        sys.exit(2)

    # --slot required for both paths
    if slot_type is None:
        click.echo("Error: --slot is required.", err=True)
        sys.exit(2)
    if slot_type not in SLOT_CAPACITIES:
        click.echo(f"Error: unknown slot '{slot_type}'. "
                   f"Valid: {', '.join(sorted(SLOT_CAPACITIES))}.", err=True)
        sys.exit(2)

    vault_path, db_path = _memory_vault_db(vault)

    # Resolve content_summary and validate record_id
    if free_text is not None:
        content_summary = free_text
        resolved_record_id: str | None = None
    else:
        # Look up content from memory_records
        conn = connect(db_path)
        try:
            row = conn.execute(
                "SELECT content FROM memory_records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            click.echo(f"Error: record_id {record_id!r} not found in vault.", err=True)
            sys.exit(2)
        content_summary = row["content"][:200]
        resolved_record_id = record_id

    with vault_lock(vault_path):
        event_log = SQLiteEventLog(db_path)

        session_id = get_active_session(db_path, str(vault_path))
        if session_id is None:
            session_id = new_session(db_path, str(vault_path), event_log)

        wm = WorkingMemory(db_path, session_id)
        try:
            item = wm.promote(
                slot_type=slot_type,
                record_id=resolved_record_id,
                content_summary=content_summary,
                salience_score=salience_score,
                is_pinned=pin,
                event_log=event_log,
            )
        except Exception as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(2)

    pin_note = "  [pinned]" if item.is_pinned else ""
    click.echo(
        f"Promoted: {item.item_id}  slot={item.slot_type}  "
        f"salience={item.salience_score:.4f}{pin_note}"
    )
    if item.record_id:
        click.echo(f"  record_id: {item.record_id}")
    click.echo(f"  session:   {item.session_id}")


@memory.command("evict")
@click.argument("item_id")
@click.option("--vault", default=None, help="Vault path (overrides env + config).")
def memory_evict(item_id: str, vault: str | None) -> None:
    """Evict an item from working memory by item_id."""
    import sys

    from cerebra.cli.lockfile import vault_lock
    from cerebra.cognition.working_memory import (
        WorkingMemory,
        get_active_session,
    )
    from cerebra.inspector.sqlite_log import SQLiteEventLog

    vault_path, db_path = _memory_vault_db(vault)

    with vault_lock(vault_path):
        session_id = get_active_session(db_path, str(vault_path))
        if session_id is None:
            click.echo("Error: no active session.", err=True)
            sys.exit(2)

        wm = WorkingMemory(db_path, session_id)
        event_log = SQLiteEventLog(db_path)
        try:
            wm.evict(item_id, reason="cli_evict", event_log=event_log)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(2)

    click.echo(f"Evicted: {item_id}")


# ── run-cycle ─────────────────────────────────────────────────────────────────


@cli.command("run-cycle")
@click.argument("config_name")
@click.option("--goal", required=True, help="Goal for this cognitive cycle.")
@click.option("--vault", default=None, help="Vault path (overrides env + config).")
@click.option("--continue", "continue_session", default=None, metavar="SESSION_ID",
              help="[stub] Continue from a prior session (Phase 9).")
@click.option("--max-steps", "max_steps_override", default=None, type=int,
              help="Override max_steps from the cycle config.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Validate config and session setup; do not run the cycle.")
@click.option("--quiet", is_flag=True, default=False, help="Suppress progress output.")
@click.option("--verbose", is_flag=True, default=False, help="Emit per-step detail.")
def run_cycle(
    config_name: str,
    goal: str,
    vault: str | None,
    continue_session: str | None,
    max_steps_override: int | None,
    dry_run: bool,
    quiet: bool,
    verbose: bool,
) -> None:
    """Run a cognitive cycle against CONFIG_NAME with GOAL.

    Exit codes:
      0  Cycle completed with 'accept' outcome.
      1  Cycle halted with 'stop' or 'cap_reached' outcome.
      2  Setup or configuration error.
      3  Runtime failure (LLM error, unhandled exception).
    """
    import dataclasses
    import sys

    from cerebra.cognition.cycle_config import CycleConfigLoader, CycleConfigValidationError
    from cerebra.cognition.cycle_runtime import CycleRuntime
    from cerebra.cognition.llm_adapter import OllamaDirectAdapter
    from cerebra.cognition.session import SessionManager
    from cerebra.storage.fossic_store import FossicStore
    from cerebra.storage.migrations import run_migrations

    def _out(msg: str) -> None:
        if not quiet:
            click.echo(msg)

    def _verbose(msg: str) -> None:
        if verbose and not quiet:
            click.echo(msg)

    # ── resolve vault ─────────────────────────────────────────────────────────
    try:
        vault_path = _get_vault(vault)
    except Exception as e:
        msg = e.format_message() if isinstance(e, click.ClickException) else str(e)
        click.echo(f"Error: {msg}", err=True)
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

    # ── load cycle config ─────────────────────────────────────────────────────
    try:
        loader = CycleConfigLoader()
        cycle_config = loader.load(config_name, vault_path)
    except FileNotFoundError:
        click.echo(f"Error: cycle config {config_name!r} not found.", err=True)
        sys.exit(2)
    except CycleConfigValidationError as e:
        click.echo(f"Error: cycle config invalid: {e}", err=True)
        sys.exit(2)
    except Exception as e:
        click.echo(f"Error: could not load cycle config: {e}", err=True)
        sys.exit(2)

    # Apply max_steps override
    if max_steps_override is not None:
        cycle_config = dataclasses.replace(cycle_config, max_steps=max_steps_override)

    _verbose(f"Config: {cycle_config.name} v{cycle_config.version}  "
             f"steps: {len(cycle_config.steps)}  max: {cycle_config.max_steps}")

    if continue_session is not None:
        _out(f"Note: --continue is a stub in v0.1; SESSION_ID {continue_session!r} ignored.")

    if dry_run:
        _out(f"[dry-run] Config: {cycle_config.name}")
        _out(f"[dry-run] Goal:   {goal}")
        _out(f"[dry-run] Vault:  {vault_path}")
        _out("[dry-run] Setup OK — no cycle executed.")
        sys.exit(0)

    # ── open session ──────────────────────────────────────────────────────────
    try:
        store = FossicStore(vault_path)
        manager = SessionManager(db_path=db_path, store=store)
        session, opened_event_id = manager.open_session(
            goal=goal,
            cycle_config=config_name,
            vault_path=vault_path,
        )
    except Exception as e:
        click.echo(f"Error: could not open session: {e}", err=True)
        sys.exit(2)

    _out(f"Session: {session.session_id}")
    _out(f"Goal:    {goal}")
    _out(f"Config:  {config_name}")
    _out("")

    # ── run cycle ─────────────────────────────────────────────────────────────
    try:
        llm = OllamaDirectAdapter()
        runtime = CycleRuntime(
            config=cycle_config,
            session=session,
            db_path=db_path,
            store=store,
            llm=llm,
            opened_event_id=opened_event_id,
        )
        _out("Running cycle...")
        result = runtime.run()
    except Exception as e:
        click.echo(f"Error: cycle runtime failed: {e}", err=True)
        sys.exit(3)

    # ── output results ────────────────────────────────────────────────────────
    _out(f"Cycle:   {result.cycle_id}")
    _out(f"Outcome: {result.outcome}")
    _out(f"Steps:   {result.total_steps}")

    if verbose and not quiet:
        for sr in result.step_results:
            status = "FAILED" if sr.failed else "ok"
            _verbose(f"  step {sr.step_name}: {status}")
            if sr.output_text and not sr.failed:
                preview = sr.output_text[:120].replace("\n", " ")
                _verbose(f"    {preview}")

    if result.final_output and not quiet:
        click.echo("")
        click.echo("── Output ──")
        click.echo(result.final_output)

    # ── exit code ─────────────────────────────────────────────────────────────
    if result.outcome == "accept":
        sys.exit(0)
    else:
        sys.exit(1)
