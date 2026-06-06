"""
Unit tests for the SKU classifier — mocked LLM adapter throughout.

Tests the formula, threshold logic, D7-D8 occupancy, idempotency,
failure handling, and event emission without any real LLM calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cerebra.cognition.llm_adapter import ClassificationError, ClassificationResult, LLMAdapter
from cerebra.cognition.sku import D9Modality, D10Provenance
from cerebra.cognition.sku_categories import D1Category
from cerebra.cognition.sku_classifier import (
    CLASSIFIER_VERSION,
    PROMPT_VERSION,
    SKUClassifier,
)
from cerebra.storage.sqlite_store import SQLiteStore

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_scores(primary: str = "MECHANISM", primary_score: float = 0.85) -> dict[str, float]:
    """Build a full 16-category scores dict with one dominant value."""
    from cerebra.cognition.sku_categories import D1Category

    scores = {c.name: 0.05 for c in D1Category}
    scores[primary] = primary_score
    return scores


def _mock_result(
    primary: str = "MECHANISM",
    primary_score: float = 0.85,
    confidence: float = 0.80,
) -> ClassificationResult:
    return ClassificationResult(
        scores=_make_scores(primary, primary_score),
        confidence=confidence,
        primary=primary,
        reasoning="Test reasoning.",
        model_string="cerebra-classifier",
        latency_ms=500,
        input_tokens=800,
        output_tokens=150,
    )


class MockAdapter(LLMAdapter):
    # Map D1 category names → quadrant for classify_quadrant stub
    _CATEGORY_TO_QUADRANT: dict[str, str] = {
        "OBSERVATION": "EMPIRICAL",
        "PATTERN": "EMPIRICAL",
        "MECHANISM": "EMPIRICAL",
        "PHENOMENON": "EMPIRICAL",
        "TECHNIQUE": "GENERATIVE",
        "DESIGN": "GENERATIVE",
        "CREATION": "GENERATIVE",
        "TOOL": "GENERATIVE",
        "PRINCIPLE": "NORMATIVE",
        "JUDGMENT": "NORMATIVE",
        "GOAL": "NORMATIVE",
        "CONSTRAINT": "NORMATIVE",
        "EVENT": "RELATIONAL",
        "AGENT": "RELATIONAL",
        "CONTEXT": "RELATIONAL",
        "RELATION": "RELATIONAL",
    }

    def __init__(self, result: ClassificationResult | None = None, raise_on: int = 0) -> None:
        self._result = result or _mock_result()
        self._call_count = 0
        self._raise_on = raise_on  # raise ClassificationError on Nth call (1-indexed)

    def classify_d1(self, content: str) -> ClassificationResult:
        self._call_count += 1
        if self._raise_on and self._call_count <= self._raise_on:
            raise ClassificationError("Mock failure")
        return self._result

    def classify_quadrant(self, content: str) -> ClassificationResult:
        self._call_count += 1
        if self._raise_on and self._call_count <= self._raise_on:
            raise ClassificationError("Mock failure")
        quadrant = self._CATEGORY_TO_QUADRANT.get(self._result.primary, "EMPIRICAL")
        quadrant_scores = {
            "EMPIRICAL": 0.05,
            "GENERATIVE": 0.05,
            "NORMATIVE": 0.05,
            "RELATIONAL": 0.05,
        }
        quadrant_scores[quadrant] = 0.85
        return ClassificationResult(
            scores=quadrant_scores,
            confidence=self._result.confidence,
            primary=quadrant,
            reasoning="",
            model_string=self._result.model_string,
            latency_ms=self._result.latency_ms,
            input_tokens=self._result.input_tokens,
            output_tokens=self._result.output_tokens,
        )

    def classify_within_quadrant(self, content: str, quadrant: str) -> ClassificationResult:
        self._call_count += 1
        if self._raise_on and self._call_count <= self._raise_on:
            raise ClassificationError("Mock failure")
        return self._result

    def health_check(self) -> bool:
        return True


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    from cerebra.vault.init import init_vault

    return init_vault(tmp_path / "vault")


@pytest.fixture
def store_and_logs(vault: Path):
    from cerebra.inspector.ndjson_log import NDJSONEventLog
    from cerebra.inspector.sqlite_log import SQLiteEventLog

    db_path = vault / "data" / "cerebra.db"
    store = SQLiteStore(db_path)
    event_log = SQLiteEventLog(db_path)
    ndjson = NDJSONEventLog(vault / "events" / "test.ndjson")
    return store, event_log, ndjson


def _make_classifier(
    vault: Path,
    adapter: LLMAdapter | None = None,
) -> tuple[SKUClassifier, SQLiteStore]:
    from cerebra.inspector.ndjson_log import NDJSONEventLog
    from cerebra.inspector.sqlite_log import SQLiteEventLog

    db_path = vault / "data" / "cerebra.db"
    store = SQLiteStore(db_path)
    event_log = SQLiteEventLog(db_path)
    ndjson = NDJSONEventLog(vault / "events" / "test.ndjson")
    clf = SKUClassifier(
        store=store,
        event_log=event_log,
        ndjson=ndjson,
        adapter=adapter or MockAdapter(),
    )
    return clf, store


def _seed_record(vault: Path, store: SQLiteStore, record_id: str = "rec_test") -> None:
    """Insert a minimal source + memory_record to classify."""

    from cerebra.ingest.pipeline import ingest_path

    docs = vault.parent / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "test.md").write_text("# Test\n\n## Section\n\nSome content here.\n")
    ingest_path(vault, docs)


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestClassifierFormula:
    def test_high_score_selects_correct_d1(self, vault: Path) -> None:
        clf, store = _make_classifier(vault, MockAdapter(_mock_result("PRINCIPLE", 0.9)))
        _seed_record(vault, store)
        records = store.get_records_needing_classification(CLASSIFIER_VERSION, PROMPT_VERSION)
        assert records
        asgn = clf.classify_record(records[0]["record_id"], records[0]["content"], "markdown")
        assert asgn is not None
        assert asgn.sku_address.d1 == D1Category.PRINCIPLE

    def test_below_threshold_still_gets_best_scorer(self, vault: Path) -> None:
        scores = {c.name: 0.05 for c in D1Category}
        scores["GOAL"] = 0.35  # below 0.4 threshold, but still highest
        result = ClassificationResult(
            scores=scores,
            confidence=0.3,
            primary="GOAL",
            reasoning="test",
        )
        clf, store = _make_classifier(vault, MockAdapter(result))
        _seed_record(vault, store)
        records = store.get_records_needing_classification(CLASSIFIER_VERSION, PROMPT_VERSION)
        asgn = clf.classify_record(records[0]["record_id"], records[0]["content"], "markdown")
        assert asgn is not None
        assert asgn.sku_address.d1 == D1Category.GOAL

    def test_d9_set_from_detected_type(self, vault: Path) -> None:
        clf, store = _make_classifier(vault)
        _seed_record(vault, store)
        records = store.get_records_needing_classification(CLASSIFIER_VERSION, PROMPT_VERSION)
        asgn = clf.classify_record(records[0]["record_id"], records[0]["content"], "markdown")
        assert asgn is not None
        assert asgn.sku_address.d9 == D9Modality.TEXT

    def test_d10_always_observed(self, vault: Path) -> None:
        clf, store = _make_classifier(vault)
        _seed_record(vault, store)
        records = store.get_records_needing_classification(CLASSIFIER_VERSION, PROMPT_VERSION)
        asgn = clf.classify_record(records[0]["record_id"], records[0]["content"], "markdown")
        assert asgn is not None
        assert asgn.sku_address.d10 == D10Provenance.OBSERVED

    def test_d2_d3_d4_d5_d6_are_zero(self, vault: Path) -> None:
        clf, store = _make_classifier(vault)
        _seed_record(vault, store)
        records = store.get_records_needing_classification(CLASSIFIER_VERSION, PROMPT_VERSION)
        asgn = clf.classify_record(records[0]["record_id"], records[0]["content"], "markdown")
        assert asgn is not None
        assert asgn.sku_address.d2 == 0
        assert asgn.sku_address.d3 == 0
        assert asgn.sku_address.d4 == 0
        assert asgn.sku_address.d5 == 0
        assert asgn.sku_address.d6 == 0

    def test_subcategory_strategy_version_is_v1_stub(self, vault: Path) -> None:
        clf, store = _make_classifier(vault)
        _seed_record(vault, store)
        records = store.get_records_needing_classification(CLASSIFIER_VERSION, PROMPT_VERSION)
        asgn = clf.classify_record(records[0]["record_id"], records[0]["content"], "markdown")
        assert asgn is not None
        assert asgn.subcategory_strategy_version == "v1-stub"


@pytest.mark.unit
class TestD7D8OccupancyIndex:
    def test_first_record_at_location_gets_index_zero(self, vault: Path) -> None:
        clf, store = _make_classifier(vault, MockAdapter(_mock_result("MECHANISM", 0.9)))
        _seed_record(vault, store)
        records = store.get_records_needing_classification(CLASSIFIER_VERSION, PROMPT_VERSION)
        asgn = clf.classify_record(records[0]["record_id"], records[0]["content"], "markdown")
        assert asgn is not None
        assert asgn.sku_address.entry_index == 0

    def test_occupancy_count_queries_full_location_tuple(self, vault: Path) -> None:
        clf, store = _make_classifier(vault)
        count = store.count_sku_location_occupancy(0x2, 0, 0, 0, 0, 0, 0x0, 0x0)
        assert count == 0  # fresh vault


@pytest.mark.unit
class TestIdempotency:
    def test_already_classified_record_is_skipped(self, vault: Path) -> None:
        clf, store = _make_classifier(vault)
        _seed_record(vault, store)
        records = store.get_records_needing_classification(CLASSIFIER_VERSION, PROMPT_VERSION)
        rid = records[0]["record_id"]

        asgn1 = clf.classify_record(rid, records[0]["content"], "markdown")
        assert asgn1 is not None

        # Second call — same versions — should return None (skip)
        asgn2 = clf.classify_record(rid, records[0]["content"], "markdown")
        assert asgn2 is None

    def test_version_mismatch_triggers_reclassification(self, vault: Path) -> None:
        clf, store = _make_classifier(vault)
        _seed_record(vault, store)
        records = store.get_records_needing_classification(CLASSIFIER_VERSION, PROMPT_VERSION)
        rid = records[0]["record_id"]

        clf.classify_record(rid, records[0]["content"], "markdown")

        # Simulate version change (must commit via context manager)
        with store._conn() as conn:
            conn.execute(
                "UPDATE sku_assignments SET classifier_version = 'old' WHERE record_id = ?",
                (rid,),
            )

        new_records = store.get_records_needing_classification(CLASSIFIER_VERSION, PROMPT_VERSION)
        assert any(r["record_id"] == rid for r in new_records)


@pytest.mark.unit
class TestClassificationFailure:
    def test_both_retries_fail_returns_none(self, vault: Path) -> None:
        clf, store = _make_classifier(vault, MockAdapter(raise_on=2))
        _seed_record(vault, store)
        records = store.get_records_needing_classification(CLASSIFIER_VERSION, PROMPT_VERSION)
        result = clf.classify_record(records[0]["record_id"], records[0]["content"], "markdown")
        assert result is None

    def test_first_retry_succeeds_on_second_attempt(self, vault: Path) -> None:
        clf, store = _make_classifier(vault, MockAdapter(raise_on=1))
        _seed_record(vault, store)
        records = store.get_records_needing_classification(CLASSIFIER_VERSION, PROMPT_VERSION)
        result = clf.classify_record(records[0]["record_id"], records[0]["content"], "markdown")
        assert result is not None  # second attempt succeeded

    def test_classification_failed_event_emitted_on_total_failure(self, vault: Path) -> None:
        import sqlite3

        clf, store = _make_classifier(vault, MockAdapter(raise_on=2))
        _seed_record(vault, store)
        records = store.get_records_needing_classification(CLASSIFIER_VERSION, PROMPT_VERSION)
        clf.classify_record(records[0]["record_id"], records[0]["content"], "markdown")

        db_path = vault / "data" / "cerebra.db"
        conn = sqlite3.connect(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM inspector_events WHERE event_type = 'ClassificationFailed'"
        ).fetchone()[0]
        conn.close()
        assert count >= 1


@pytest.mark.unit
class TestLowConfidenceEvent:
    def test_low_confidence_event_emitted(self, vault: Path) -> None:
        import sqlite3

        low_conf_result = _mock_result(confidence=0.3)  # below HIGH_CONF_THRESHOLD
        clf, store = _make_classifier(vault, MockAdapter(low_conf_result))
        _seed_record(vault, store)
        records = store.get_records_needing_classification(CLASSIFIER_VERSION, PROMPT_VERSION)
        clf.classify_record(records[0]["record_id"], records[0]["content"], "markdown")

        db_path = vault / "data" / "cerebra.db"
        conn = sqlite3.connect(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM inspector_events WHERE event_type = 'ClassificationLowConfidence'"
        ).fetchone()[0]
        conn.close()
        assert count >= 1

    def test_high_confidence_no_low_conf_event(self, vault: Path) -> None:
        import sqlite3

        clf, store = _make_classifier(vault, MockAdapter(_mock_result(confidence=0.9)))
        _seed_record(vault, store)
        records = store.get_records_needing_classification(CLASSIFIER_VERSION, PROMPT_VERSION)
        clf.classify_record(records[0]["record_id"], records[0]["content"], "markdown")

        db_path = vault / "data" / "cerebra.db"
        conn = sqlite3.connect(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM inspector_events WHERE event_type = 'ClassificationLowConfidence'"
        ).fetchone()[0]
        conn.close()
        assert count == 0


@pytest.mark.unit
class TestBackfill:
    def test_dry_run_finds_records_writes_nothing(self, vault: Path) -> None:
        import sqlite3

        clf, store = _make_classifier(vault)
        _seed_record(vault, store)
        report = clf.backfill_null_records(dry_run=True)
        assert report.records_found > 0

        db_path = vault / "data" / "cerebra.db"
        conn = sqlite3.connect(db_path)
        null_count = conn.execute(
            "SELECT COUNT(*) FROM memory_records WHERE sku_address IS NULL"
        ).fetchone()[0]
        conn.close()
        assert null_count == report.records_found  # nothing written

    def test_backfill_classifies_all_null_records(self, vault: Path) -> None:
        import sqlite3

        clf, store = _make_classifier(vault)
        _seed_record(vault, store)
        report = clf.backfill_null_records(dry_run=False)
        assert report.classified > 0
        assert report.failed == 0

        db_path = vault / "data" / "cerebra.db"
        conn = sqlite3.connect(db_path)
        null_count = conn.execute(
            "SELECT COUNT(*) FROM memory_records WHERE sku_address IS NULL"
        ).fetchone()[0]
        conn.close()
        assert null_count == 0
