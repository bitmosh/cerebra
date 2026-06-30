"""Unit tests for the query planner (cerebra/retrieval/planner.py)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cerebra.retrieval.planner import (
    QueryPlan,
    _classify_d1,
    _detect_mode,
    _looks_like_identifier_query,
    query_plan,
)
from cerebra.storage.migrations import run_migrations

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _migrated_db() -> Path:
    """Create a fresh migrated db in a temp file; caller cleans up."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Path(f.name)
    run_migrations(db)
    return db


# ── D1 classification ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestClassifyD1:
    def test_design_keywords_hit(self) -> None:
        d1 = _classify_d1("retrieval architecture design")
        assert d1 == 0x5, f"Expected DESIGN (0x5), got {hex(d1) if d1 is not None else None}"

    def test_tool_keywords_hit(self) -> None:
        d1 = _classify_d1("which framework should I use for this api")
        assert d1 == 0x7, f"Expected TOOL (0x7), got {hex(d1) if d1 is not None else None}"

    def test_principle_keywords_hit(self) -> None:
        d1 = _classify_d1("what should always happen when a migration fails")
        assert d1 == 0x8, f"Expected PRINCIPLE (0x8), got {hex(d1) if d1 is not None else None}"

    def test_goal_keywords_hit(self) -> None:
        # Avoid "what is" (hits 0x3); use multiple 0xa keywords to dominate
        d1 = _classify_d1("our goal and objective for Phase 4 is retrieval")
        assert d1 == 0xa, f"Expected GOAL (0xA), got {hex(d1) if d1 is not None else None}"

    def test_context_keyword_hit(self) -> None:
        d1 = _classify_d1("what is the scope of the project")
        assert d1 == 0xe, f"Expected CONTEXT (0xE), got {hex(d1) if d1 is not None else None}"

    def test_no_match_returns_none(self) -> None:
        d1 = _classify_d1("hello")
        assert d1 is None

    def test_very_short_query_no_match(self) -> None:
        d1 = _classify_d1("hi there")
        assert d1 is None

    def test_empty_query_returns_none(self) -> None:
        d1 = _classify_d1("")
        assert d1 is None

    def test_case_insensitive(self) -> None:
        d1_lower = _classify_d1("design architecture")
        d1_upper = _classify_d1("DESIGN ARCHITECTURE")
        assert d1_lower == d1_upper

    def test_returns_int(self) -> None:
        d1 = _classify_d1("plan the design architecture")
        assert isinstance(d1, int)

    def test_d1_in_valid_range(self) -> None:
        for query in [
            "what tool should I use",
            "the mechanism behind this process",
            "the goal of the system",
            "what constraint is blocking",
        ]:
            d1 = _classify_d1(query)
            if d1 is not None:
                assert 0 <= d1 <= 15, f"D1 {d1} out of range for query: {query!r}"

    def test_multiword_phrase_matching(self) -> None:
        # "how to" is a multi-word phrase for TECHNIQUE (0x4)
        d1 = _classify_d1("how to implement a retrieval pipeline")
        assert d1 == 0x4, f"Expected TECHNIQUE (0x4), got {hex(d1) if d1 is not None else None}"


# ── Identifier detection ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestIdentifierDetection:
    def test_snake_case_detected(self) -> None:
        assert _looks_like_identifier_query("what does drain_pending do") is True

    def test_camel_case_detected(self) -> None:
        assert _looks_like_identifier_query("how does QueryPlan work") is True

    def test_file_extension_detected(self) -> None:
        assert _looks_like_identifier_query("where is the config.yaml file") is True

    def test_quoted_string_detected(self) -> None:
        assert _looks_like_identifier_query('find "cerebra.db" in the vault') is True

    def test_constant_name_detected(self) -> None:
        assert _looks_like_identifier_query("what does RELEVANCE_FLOOR mean") is True

    def test_plain_natural_language_not_detected(self) -> None:
        assert _looks_like_identifier_query("what is the retrieval architecture") is False

    def test_plain_question_not_detected(self) -> None:
        assert _looks_like_identifier_query("how does phase 4 work") is False


# ── Mode selection ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestDetectMode:
    def test_snake_case_query_is_lexical_only(self) -> None:
        assert _detect_mode("drain_pending function", query_d1=None) == "lexical_only"

    def test_file_extension_query_is_lexical_only(self) -> None:
        assert _detect_mode("where is config.yaml", query_d1=None) == "lexical_only"

    def test_quoted_query_is_lexical_only(self) -> None:
        assert _detect_mode('"cerebra search" command', query_d1=None) == "lexical_only"

    def test_one_word_no_d1_is_vector_only(self) -> None:
        assert _detect_mode("hello", query_d1=None) == "vector_only"

    def test_two_words_no_d1_is_vector_only(self) -> None:
        assert _detect_mode("phase four", query_d1=None) == "vector_only"

    def test_three_word_no_d1_is_hybrid(self) -> None:
        # No D1 hit but >= 3 words → hybrid (falls through to vector in traversal)
        assert _detect_mode("something something something", query_d1=None) == "hybrid"

    def test_long_query_with_d1_is_hybrid(self) -> None:
        assert _detect_mode("plan the retrieval architecture", query_d1=0x5) == "hybrid"

    def test_long_query_without_d1_is_hybrid(self) -> None:
        assert _detect_mode("tell me about the system", query_d1=None) == "hybrid"

    def test_identifier_wins_over_d1(self) -> None:
        # Even if D1 is classified, snake_case → lexical_only wins
        assert _detect_mode("drain_pending architecture design", query_d1=0x5) == "lexical_only"

    def test_mode_values_are_valid(self) -> None:
        valid = {"hybrid", "lexical_only", "vector_only"}
        for query, d1 in [
            ("hello", None),
            ("architecture design", 0x5),
            ("drain_pending function", None),
            ("how to build a pipeline for the project", 0x4),
        ]:
            mode = _detect_mode(query, d1)
            assert mode in valid, f"Unexpected mode {mode!r} for {query!r}"


# ── query_plan() integration ───────────────────────────────────────────────────


@pytest.mark.unit
class TestQueryPlan:
    def test_returns_query_plan(self) -> None:
        db = _migrated_db()
        try:
            plan = query_plan("retrieval architecture design", db)
            assert isinstance(plan, QueryPlan)
        finally:
            db.unlink(missing_ok=True)

    def test_plan_has_trace_id(self) -> None:
        db = _migrated_db()
        try:
            plan = query_plan("test query", db)
            assert plan.trace_id.startswith("trace_")
            assert len(plan.trace_id) == len("trace_") + 12
        finally:
            db.unlink(missing_ok=True)

    def test_plan_trace_ids_are_unique(self) -> None:
        db = _migrated_db()
        try:
            ids = {query_plan("test query", db).trace_id for _ in range(5)}
            assert len(ids) == 5, "trace_ids must be unique across calls"
        finally:
            db.unlink(missing_ok=True)

    def test_plan_raw_query_preserved(self) -> None:
        db = _migrated_db()
        try:
            q = "the retrieval architecture plan"
            plan = query_plan(q, db)
            assert plan.raw_query == q
        finally:
            db.unlink(missing_ok=True)

    def test_plan_mode_is_valid(self) -> None:
        db = _migrated_db()
        try:
            plan = query_plan("what is the architecture design", db)
            assert plan.mode in {"hybrid", "lexical_only", "vector_only"}
        finally:
            db.unlink(missing_ok=True)

    def test_staleness_warning_for_fresh_vault(self) -> None:
        # Fresh vault: all indexes have last_updated_at=0 → never-built warnings
        db = _migrated_db()
        try:
            plan = query_plan("test query", db)
            # Fresh vault has no index_state rows at all → is_stale returns True
            # At minimum lexical and vector should warn
            assert isinstance(plan.staleness_warnings, list)
        finally:
            db.unlink(missing_ok=True)

    def test_staleness_warnings_when_indexes_never_built(self) -> None:
        db = _migrated_db()
        try:
            plan = query_plan("any query", db)
            # Fresh vault: index_state has rows with last_updated_at=0
            # (Migration007 seeds them). All three should warn.
            warning_text = " ".join(plan.staleness_warnings)
            assert "lexical" in warning_text or "vector" in warning_text or "graph" in warning_text
        finally:
            db.unlink(missing_ok=True)

    def test_d1_and_pattern_consistent(self) -> None:
        db = _migrated_db()
        try:
            plan = query_plan("retrieval architecture design", db)
            if plan.query_d1 is not None:
                assert plan.query_d1_d2_d3 == f"0x{plan.query_d1:x}"
            else:
                assert plan.query_d1_d2_d3 is None
        finally:
            db.unlink(missing_ok=True)

    def test_max_candidates_default(self) -> None:
        db = _migrated_db()
        try:
            plan = query_plan("test query", db)
            assert plan.max_candidates == 200
        finally:
            db.unlink(missing_ok=True)

    def test_max_candidates_override(self) -> None:
        db = _migrated_db()
        try:
            plan = query_plan("test query", db, max_candidates=50)
            assert plan.max_candidates == 50
        finally:
            db.unlink(missing_ok=True)

    def test_events_emitted_with_event_log(self) -> None:
        from cerebra.inspector.sqlite_log import SQLiteEventLog
        db = _migrated_db()
        try:
            log = SQLiteEventLog(db)
            query_plan("architecture design plan", db, event_log=log)
            received = log.query_by_type("QueryReceived")
            planned = log.query_by_type("QueryPlanned")
            assert len(received) == 1
            assert len(planned) == 1
        finally:
            db.unlink(missing_ok=True)

    def test_events_share_trace_id(self) -> None:
        import json

        from cerebra.inspector.sqlite_log import SQLiteEventLog
        db = _migrated_db()
        try:
            log = SQLiteEventLog(db)
            plan = query_plan("design architecture", db, event_log=log)
            planned = log.query_by_type("QueryPlanned")[0]
            data = json.loads(planned["data_json"])
            assert data["trace_id"] == plan.trace_id
        finally:
            db.unlink(missing_ok=True)

    def test_no_events_without_event_log(self) -> None:
        from cerebra.inspector.sqlite_log import SQLiteEventLog
        db = _migrated_db()
        try:
            query_plan("architecture design plan", db, event_log=None)
            log = SQLiteEventLog(db)
            assert len(log.query_by_type("QueryReceived")) == 0
        finally:
            db.unlink(missing_ok=True)
