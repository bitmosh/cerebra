# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the ingest pipeline."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cerebra.ingest.pipeline import ingest_path
from cerebra.vault.init import init_vault

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    return init_vault(tmp_path / "vault")


@pytest.fixture
def docs_dir(tmp_path: Path) -> Path:
    d = tmp_path / "docs"
    d.mkdir()
    (d / "scope.md").write_text(
        "# Scope\n\nCerebra is a cognitive runtime.\n\n## Goals\n\nBuild something real.\n"
    )
    (d / "architecture.md").write_text(
        "# Architecture\n\nThe system spine.\n\n## Components\n\nMany parts.\n"
    )
    (d / "notes.txt").write_text("Some plain text notes.\n")
    return d


def _db(vault: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(vault / "data" / "cerebra.db")
    conn.row_factory = sqlite3.Row
    return conn


# ── Happy path ────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestIngestHappyPath:
    def test_registers_all_files(self, vault: Path, docs_dir: Path) -> None:
        report = ingest_path(vault, docs_dir)
        assert report.sources_found == 3
        assert report.sources_new == 3
        assert report.sources_failed == 0

    def test_creates_chunks_for_each_source(self, vault: Path, docs_dir: Path) -> None:
        report = ingest_path(vault, docs_dir)
        assert report.chunks_created > 0

    def test_creates_memory_records(self, vault: Path, docs_dir: Path) -> None:
        report = ingest_path(vault, docs_dir)
        assert report.records_created > 0
        assert report.records_created == report.chunks_created

    def test_no_orphan_chunks(self, vault: Path, docs_dir: Path) -> None:
        ingest_path(vault, docs_dir)
        with _db(vault) as conn:
            orphans = conn.execute(
                """
                SELECT COUNT(*) FROM chunks c
                LEFT JOIN documents d ON c.document_id = d.document_id
                WHERE d.document_id IS NULL
            """
            ).fetchone()[0]
        assert orphans == 0

    def test_no_orphan_records(self, vault: Path, docs_dir: Path) -> None:
        ingest_path(vault, docs_dir)
        with _db(vault) as conn:
            orphans = conn.execute(
                """
                SELECT COUNT(*) FROM memory_records r
                LEFT JOIN chunks c ON r.chunk_id = c.chunk_id
                WHERE c.chunk_id IS NULL
            """
            ).fetchone()[0]
        assert orphans == 0

    def test_all_records_have_null_sku(self, vault: Path, docs_dir: Path) -> None:
        ingest_path(vault, docs_dir)
        with _db(vault) as conn:
            with_sku = conn.execute(
                "SELECT COUNT(*) FROM memory_records WHERE sku_address IS NOT NULL"
            ).fetchone()[0]
        assert with_sku == 0  # Phase 2 fills these

    def test_sources_have_active_lifecycle(self, vault: Path, docs_dir: Path) -> None:
        ingest_path(vault, docs_dir)
        with _db(vault) as conn:
            non_active = conn.execute(
                "SELECT COUNT(*) FROM sources WHERE lifecycle_state != 'active'"
            ).fetchone()[0]
        assert non_active == 0

    def test_inspector_events_emitted(self, vault: Path, docs_dir: Path) -> None:
        ingest_path(vault, docs_dir)
        with _db(vault) as conn:
            source_events = conn.execute(
                "SELECT COUNT(*) FROM inspector_events WHERE event_type = 'SourceRegistered'"
            ).fetchone()[0]
            chunk_events = conn.execute(
                "SELECT COUNT(*) FROM inspector_events WHERE event_type = 'ChunkCreated'"
            ).fetchone()[0]
        assert source_events >= 3
        assert chunk_events > 0

    def test_graph_node_events_emitted(self, vault: Path, docs_dir: Path) -> None:
        ingest_path(vault, docs_dir)
        with _db(vault) as conn:
            node_events = conn.execute(
                "SELECT COUNT(*) FROM inspector_events WHERE event_type = 'GraphNodeCreated'"
            ).fetchone()[0]
            edge_events = conn.execute(
                "SELECT COUNT(*) FROM inspector_events WHERE event_type = 'GraphEdgeCreated'"
            ).fetchone()[0]
        assert node_events > 0
        assert edge_events > 0

    def test_graph_tables_populated(self, vault: Path, docs_dir: Path) -> None:
        ingest_path(vault, docs_dir)
        with _db(vault) as conn:
            node_count = conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]
            edge_count = conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]
        assert node_count > 0
        assert edge_count > 0

    def test_document_artifact_events_emitted(self, vault: Path, docs_dir: Path) -> None:
        ingest_path(vault, docs_dir)
        with _db(vault) as conn:
            artifact_events = conn.execute(
                "SELECT COUNT(*) FROM inspector_events WHERE event_type = 'DocumentArtifactWritten'"
            ).fetchone()[0]
        assert artifact_events == 3  # one per source file

    def test_lexical_index_event_emitted(self, vault: Path, docs_dir: Path) -> None:
        ingest_path(vault, docs_dir)
        with _db(vault) as conn:
            lexical_events = conn.execute(
                "SELECT COUNT(*) FROM inspector_events WHERE event_type = 'LexicalIndexUpdated'"
            ).fetchone()[0]
        assert lexical_events > 0

    def test_embeddings_queued(self, vault: Path, docs_dir: Path) -> None:
        ingest_path(vault, docs_dir)
        with _db(vault) as conn:
            pending = conn.execute("SELECT COUNT(*) FROM pending_embeddings").fetchone()[0]
        assert pending > 0

    def test_artifacts_written(self, vault: Path, docs_dir: Path) -> None:
        ingest_path(vault, docs_dir)
        artifacts = list((vault / "artifacts").glob("*.json"))
        assert len(artifacts) == 3


# ── Idempotency ───────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestIdempotency:
    def test_re_ingest_unchanged_is_noop(self, vault: Path, docs_dir: Path) -> None:
        ingest_path(vault, docs_dir)
        report2 = ingest_path(vault, docs_dir)
        assert report2.sources_skipped == 3
        assert report2.sources_new == 0
        assert report2.chunks_created == 0

    def test_record_count_unchanged_after_re_ingest(self, vault: Path, docs_dir: Path) -> None:
        ingest_path(vault, docs_dir)
        with _db(vault) as conn:
            count1 = conn.execute(
                "SELECT COUNT(*) FROM memory_records WHERE lifecycle_state = 'active'"
            ).fetchone()[0]
        ingest_path(vault, docs_dir)
        with _db(vault) as conn:
            count2 = conn.execute(
                "SELECT COUNT(*) FROM memory_records WHERE lifecycle_state = 'active'"
            ).fetchone()[0]
        assert count1 == count2

    def test_changed_file_marks_old_stale(self, vault: Path, docs_dir: Path) -> None:
        ingest_path(vault, docs_dir)
        (docs_dir / "scope.md").write_text("# New Scope\n\nCompletely different.\n")
        report2 = ingest_path(vault, docs_dir)
        assert report2.sources_changed == 1
        with _db(vault) as conn:
            stale = conn.execute(
                "SELECT COUNT(*) FROM memory_records WHERE lifecycle_state = 'stale'"
            ).fetchone()[0]
        assert stale > 0

    def test_parser_version_bump_re_ingests(self, vault: Path, docs_dir: Path) -> None:
        """Simulated by patching PARSER_VERSION in the registry call signature."""
        from cerebra.ingest import pipeline as pipe

        ingest_path(vault, docs_dir)
        # Patch: change parser version to force re-ingest
        original = pipe.MD_PARSER_VERSION
        pipe.MD_PARSER_VERSION = "9.9.9"
        pipe._PARSER_VERSION_MAP["markdown"] = "9.9.9"
        try:
            report2 = ingest_path(vault, docs_dir)
            # Markdown files should be re-ingested (version mismatch)
            assert report2.sources_changed + report2.sources_new >= 2
        finally:
            pipe.MD_PARSER_VERSION = original
            pipe._PARSER_VERSION_MAP["markdown"] = original


# ── Dry run ───────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestDryRun:
    def test_dry_run_discovers_files(self, vault: Path, docs_dir: Path) -> None:
        report = ingest_path(vault, docs_dir, dry_run=True)
        assert report.sources_found == 3

    def test_dry_run_writes_nothing(self, vault: Path, docs_dir: Path) -> None:
        ingest_path(vault, docs_dir, dry_run=True)
        with _db(vault) as conn:
            sources = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
            chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert sources == 0
        assert chunks == 0


# ── CLI ───────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestIngestCLI:
    def test_cli_ingest_basic(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        vault = init_vault(tmp_path / "vault")
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "test.md").write_text("# Test\n\nContent.\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", str(docs), "--vault", str(vault)])
        assert result.exit_code == 0
        assert "Ingest complete" in result.output

    def test_cli_ingest_dry_run(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        vault = init_vault(tmp_path / "vault")
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "test.md").write_text("# Test\n\nContent.\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", str(docs), "--vault", str(vault), "--dry-run"])
        assert result.exit_code == 0
        assert "[dry-run]" in result.output

    def test_cli_ingest_json_output(self, tmp_path: Path) -> None:
        import json

        from click.testing import CliRunner

        from cerebra.cli.main import cli

        vault = init_vault(tmp_path / "vault")
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "test.md").write_text("# Test\n\nContent.\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", str(docs), "--vault", str(vault), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "sources_found" in data
        assert "chunks_created" in data

    def test_cli_ingest_exclude(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        vault = init_vault(tmp_path / "vault")
        docs = tmp_path / "docs"
        docs.mkdir()
        skip = docs / "skip"
        skip.mkdir()
        (skip / "ignored.md").write_text("ignored")
        (docs / "keep.md").write_text("# Keep\n\nContent.\n")

        runner = CliRunner()
        result = runner.invoke(
            cli, ["ingest", str(docs), "--vault", str(vault), "--exclude", "skip", "--json"]
        )
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert data["sources_found"] == 1


# ── parse_warnings (Bug 2 regression) ────────────────────────────────────────


@pytest.mark.integration
class TestParseWarnings:
    def test_parse_warnings_stored_on_document_row(self, tmp_path: Path) -> None:
        """Out-of-order headings → parse_warnings column populated."""
        vault = init_vault(tmp_path / "vault")
        docs = tmp_path / "docs"
        docs.mkdir()
        # H1 → H3 directly (depth jump: triggers warning)
        (docs / "jumpy.md").write_text("# Title\n\n### Skipped H2\n\nContent.\n")

        ingest_path(vault, docs)

        with _db(vault) as conn:
            row = conn.execute(
                "SELECT parse_warnings FROM documents WHERE parse_warnings IS NOT NULL"
            ).fetchone()
        assert row is not None, "Expected parse_warnings to be populated for depth-jump doc"
        import json

        warnings = json.loads(row[0])
        assert len(warnings) >= 1
        assert any("H1" in w or "jump" in w.lower() or "depth" in w.lower() for w in warnings)

    def test_documentparsewarning_event_emitted(self, tmp_path: Path) -> None:
        """Out-of-order headings → DocumentParseWarning inspector event emitted."""
        vault = init_vault(tmp_path / "vault")
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "jumpy.md").write_text("# Title\n\n### Skipped H2\n\nContent.\n")

        ingest_path(vault, docs)

        with _db(vault) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM inspector_events WHERE event_type = 'DocumentParseWarning'"
            ).fetchone()[0]
        assert count >= 1, "Expected at least one DocumentParseWarning event"

    def test_clean_doc_has_null_parse_warnings(self, tmp_path: Path) -> None:
        vault = init_vault(tmp_path / "vault")
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "clean.md").write_text("# Title\n\n## Section\n\nContent.\n")

        ingest_path(vault, docs)

        with _db(vault) as conn:
            row = conn.execute("SELECT parse_warnings FROM documents").fetchone()
        assert row is not None
        assert row[0] is None  # no warnings for well-structured doc


# ── cerebra status ────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestStatusCommand:
    def test_status_shows_vault_summary(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from cerebra.cli.main import cli

        vault = init_vault(tmp_path / "vault")
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "test.md").write_text("# Test\n\n## Section\n\nContent.\n")
        ingest_path(vault, docs)

        runner = CliRunner()
        result = runner.invoke(cli, ["status", "--vault", str(vault)])
        assert result.exit_code == 0
        assert "Vault:" in result.output
        assert "Sources:" in result.output
        assert "Chunks:" in result.output
        assert "wal" in result.output.lower()  # WAL mode confirmed
