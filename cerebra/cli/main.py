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
def context(
    query: str,
    vault: str | None,
    limit: int,
    relevance_floor: float,
    output_format: str,
    out_file: str | None,
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
