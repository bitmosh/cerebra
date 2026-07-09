# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for Interpretive Lattice Phase 1.

Covers:
  - evaluate_lattice() threshold logic and sorting
  - LatticeDecision.should_multi_commit
  - new_lineage_id() format
  - build_sibling_record_id() determinism and per-category uniqueness
  - classify_record_lattice() single-commit path (no LatticeCommit event)
  - classify_record_lattice() multi-commit path (LatticeCommit emitted, siblings in DB)
  - classify_record_lattice() failure path (ClassificationError → returns [])
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cerebra.cognition.lattice import (
    build_sibling_record_id,
    evaluate_lattice,
    new_lineage_id,
)
from cerebra.cognition.llm_adapter import ClassificationError, ClassificationResult, LLMAdapter
from cerebra.cognition.sku_categories import D1Category
from cerebra.cognition.sku_classifier import SKUClassifier
from cerebra.storage.sqlite_store import SQLiteStore

# ── helpers ───────────────────────────────────────────────────────────────────


def _low_scores(exclude: list[str] | None = None) -> dict[str, float]:
    """All categories at 0.05, with named exceptions set to 0.0."""
    scores = {c.name: 0.05 for c in D1Category}
    for name in exclude or []:
        scores[name] = 0.0
    return scores


def _scores_with(**kwargs: float) -> dict[str, float]:
    """All categories at 0.05 except those overridden by kwargs."""
    base = {c.name: 0.05 for c in D1Category}
    base.update(kwargs)
    return base


class MockAdapter(LLMAdapter):
    _QUADRANT_MAP: dict[str, str] = {
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

    def __init__(
        self,
        result: ClassificationResult | None = None,
        raise_error: bool = False,
    ) -> None:
        self._result = result or ClassificationResult(
            scores=_scores_with(MECHANISM=0.85),
            confidence=0.80,
            primary="MECHANISM",
            reasoning="test",
        )
        self._raise_error = raise_error

    def classify_quadrant(self, content: str) -> ClassificationResult:
        if self._raise_error:
            raise ClassificationError("Mock failure")
        quadrant = self._QUADRANT_MAP.get(self._result.primary, "EMPIRICAL")
        q_scores = dict.fromkeys(("EMPIRICAL", "GENERATIVE", "NORMATIVE", "RELATIONAL"), 0.05)
        q_scores[quadrant] = 0.85
        return ClassificationResult(
            scores=q_scores,
            confidence=self._result.confidence,
            primary=quadrant,
            reasoning="",
            model_string=self._result.model_string,
            latency_ms=self._result.latency_ms,
            input_tokens=self._result.input_tokens,
            output_tokens=self._result.output_tokens,
        )

    def classify_d1(self, content: str) -> ClassificationResult:
        if self._raise_error:
            raise ClassificationError("Mock failure")
        return self._result

    def classify_within_quadrant(self, content: str, quadrant: str) -> ClassificationResult:
        if self._raise_error:
            raise ClassificationError("Mock failure")
        return self._result

    def health_check(self) -> bool:
        return True


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    from cerebra.vault.init import init_vault

    return init_vault(tmp_path / "vault")


def _make_classifier(
    vault: Path, adapter: LLMAdapter | None = None
) -> tuple[SKUClassifier, SQLiteStore]:
    from cerebra.inspector.ndjson_log import NDJSONEventLog
    from cerebra.inspector.sqlite_log import SQLiteEventLog

    db_path = vault / "data" / "cerebra.db"
    store = SQLiteStore(db_path)
    event_log = SQLiteEventLog(db_path)
    ndjson = NDJSONEventLog(vault / "events" / "test.ndjson")
    clf = SKUClassifier(
        store=store, event_log=event_log, ndjson=ndjson, adapter=adapter or MockAdapter()
    )
    return clf, store


def _seed_record(vault: Path) -> str:
    """Ingest one markdown file and return the first record_id."""
    from cerebra.ingest.pipeline import ingest_path

    docs = vault.parent / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "sample.md").write_text("# Lattice test\n\nContent for lattice classification.\n")
    ingest_path(vault, docs)

    from cerebra.storage.sqlite_store import SQLiteStore as _Store

    store = _Store(vault / "data" / "cerebra.db")
    records = store.get_records_needing_classification("1.0.0", "2.0.0")
    assert records, "No records seeded"
    return records[0]["record_id"]


def _count_events(vault: Path, event_type: str) -> int:
    from cerebra.storage.db import connect

    conn = connect(vault / "data" / "cerebra.db")
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM inspector_events WHERE event_type = ?",
            (event_type,),
        ).fetchone()[0]
    finally:
        conn.close()


# ── evaluate_lattice() ────────────────────────────────────────────────────────


@pytest.mark.unit
class TestEvaluateLattice:
    def test_all_below_threshold_returns_empty(self) -> None:
        scores = _low_scores()
        decision = evaluate_lattice(scores, threshold=0.65)
        assert decision.candidates == []
        assert not decision.should_multi_commit

    def test_single_category_at_threshold(self) -> None:
        scores = _scores_with(MECHANISM=0.65)
        decision = evaluate_lattice(scores, threshold=0.65)
        assert len(decision.candidates) == 1
        assert decision.candidates[0] == ("MECHANISM", 0.65)
        assert not decision.should_multi_commit

    def test_two_categories_above_threshold_triggers_multi_commit(self) -> None:
        scores = _scores_with(MECHANISM=0.85, PATTERN=0.70)
        decision = evaluate_lattice(scores, threshold=0.65)
        assert len(decision.candidates) == 2
        assert decision.should_multi_commit

    def test_candidates_sorted_descending_by_confidence(self) -> None:
        scores = _scores_with(PATTERN=0.70, MECHANISM=0.85, DESIGN=0.66)
        decision = evaluate_lattice(scores, threshold=0.65)
        confidences = [c for _, c in decision.candidates]
        assert confidences == sorted(confidences, reverse=True)

    def test_threshold_used_recorded(self) -> None:
        scores = _scores_with(MECHANISM=0.80)
        decision = evaluate_lattice(scores, threshold=0.72)
        assert decision.threshold_used == 0.72

    def test_top1_accessors(self) -> None:
        scores = _scores_with(MECHANISM=0.85, PATTERN=0.70)
        decision = evaluate_lattice(scores, threshold=0.65)
        assert decision.top_1_category == "MECHANISM"
        assert decision.top_1_confidence == 0.85

    def test_below_threshold_just_misses(self) -> None:
        scores = _scores_with(MECHANISM=0.64)
        decision = evaluate_lattice(scores, threshold=0.65)
        assert decision.candidates == []


# ── lineage ID and sibling ID helpers ────────────────────────────────────────


@pytest.mark.unit
class TestLatticeHelpers:
    def test_new_lineage_id_prefix(self) -> None:
        lid = new_lineage_id()
        assert lid.startswith("lat_")
        assert len(lid) == 16  # "lat_" + 12 hex chars

    def test_new_lineage_id_unique(self) -> None:
        ids = {new_lineage_id() for _ in range(50)}
        assert len(ids) == 50

    def test_build_sibling_record_id_prefix(self) -> None:
        sid = build_sibling_record_id("rec_abc123", "PATTERN")
        assert sid.startswith("rec_")

    def test_build_sibling_record_id_deterministic(self) -> None:
        a = build_sibling_record_id("rec_abc123", "PATTERN")
        b = build_sibling_record_id("rec_abc123", "PATTERN")
        assert a == b

    def test_build_sibling_record_id_unique_per_category(self) -> None:
        ids = {build_sibling_record_id("rec_abc123", cat.name) for cat in D1Category}
        assert len(ids) == len(list(D1Category))

    def test_build_sibling_record_id_different_primary_different_sibling(self) -> None:
        a = build_sibling_record_id("rec_aaa", "PATTERN")
        b = build_sibling_record_id("rec_bbb", "PATTERN")
        assert a != b


# ── classify_record_lattice() ─────────────────────────────────────────────────


@pytest.mark.unit
class TestClassifyRecordLattice:
    def test_single_commit_returns_primary_id_only(self, vault: Path) -> None:
        """One category above threshold → [record_id], no LatticeCommit event."""
        record_id = _seed_record(vault)
        scores = _scores_with(MECHANISM=0.80)
        adapter = MockAdapter(
            ClassificationResult(
                scores=scores, confidence=0.80, primary="MECHANISM", reasoning="single"
            )
        )
        clf, _ = _make_classifier(vault, adapter)
        result = clf.classify_record_lattice(record_id, "test content", "markdown")
        assert result == [record_id]
        assert _count_events(vault, "LatticeCommit") == 0

    def test_multi_commit_returns_all_record_ids(self, vault: Path) -> None:
        """Two categories above threshold → primary + sibling returned."""
        record_id = _seed_record(vault)
        scores = _scores_with(MECHANISM=0.85, PATTERN=0.70)
        adapter = MockAdapter(
            ClassificationResult(
                scores=scores, confidence=0.85, primary="MECHANISM", reasoning="multi"
            )
        )
        clf, store = _make_classifier(vault, adapter)
        result = clf.classify_record_lattice(record_id, "test content", "markdown")
        assert len(result) == 2
        assert result[0] == record_id  # primary always first
        assert result[1] != record_id

    def test_multi_commit_sibling_written_to_db(self, vault: Path) -> None:
        """Sibling record exists in memory_records with is_lattice_member=1."""
        record_id = _seed_record(vault)
        scores = _scores_with(MECHANISM=0.85, PATTERN=0.70)
        adapter = MockAdapter(
            ClassificationResult(
                scores=scores, confidence=0.85, primary="MECHANISM", reasoning="multi"
            )
        )
        clf, store = _make_classifier(vault, adapter)
        all_ids = clf.classify_record_lattice(record_id, "test content", "markdown")
        sibling_id = all_ids[1]

        sibling = store.get_record(sibling_id)
        assert sibling is not None
        assert sibling["is_lattice_member"] == 1
        assert sibling["lattice_confidence"] == pytest.approx(0.70, abs=1e-6)

    def test_multi_commit_primary_marked_as_lattice_member(self, vault: Path) -> None:
        """Primary record is also updated with is_lattice_member=1 on multi-commit."""
        record_id = _seed_record(vault)
        scores = _scores_with(MECHANISM=0.85, PATTERN=0.70)
        adapter = MockAdapter(
            ClassificationResult(
                scores=scores, confidence=0.85, primary="MECHANISM", reasoning="multi"
            )
        )
        clf, store = _make_classifier(vault, adapter)
        clf.classify_record_lattice(record_id, "test content", "markdown")

        primary = store.get_record(record_id)
        assert primary is not None
        assert primary["is_lattice_member"] == 1

    def test_multi_commit_siblings_share_lineage_id(self, vault: Path) -> None:
        """Primary and sibling share the same lattice_lineage_id."""
        record_id = _seed_record(vault)
        scores = _scores_with(MECHANISM=0.85, PATTERN=0.70)
        adapter = MockAdapter(
            ClassificationResult(
                scores=scores, confidence=0.85, primary="MECHANISM", reasoning="multi"
            )
        )
        clf, store = _make_classifier(vault, adapter)
        all_ids = clf.classify_record_lattice(record_id, "test content", "markdown")

        lineages = {
            store.get_record(rid)["lattice_lineage_id"] for rid in all_ids  # type: ignore[index]
        }
        assert len(lineages) == 1  # all share the same lineage_id
        assert list(lineages)[0] is not None
        assert list(lineages)[0].startswith("lat_")

    def test_lattice_commit_event_emitted_once(self, vault: Path) -> None:
        """ONE LatticeCommit event per chunk, not per sibling."""
        record_id = _seed_record(vault)
        scores = _scores_with(MECHANISM=0.85, PATTERN=0.70, DESIGN=0.66)
        adapter = MockAdapter(
            ClassificationResult(
                scores=scores, confidence=0.85, primary="MECHANISM", reasoning="multi"
            )
        )
        clf, _ = _make_classifier(vault, adapter)
        clf.classify_record_lattice(record_id, "test content", "markdown")
        assert _count_events(vault, "LatticeCommit") == 1

    def test_lattice_commit_event_data(self, vault: Path) -> None:
        """LatticeCommit event data matches the committed record_ids."""
        import json

        from cerebra.storage.db import connect

        record_id = _seed_record(vault)
        scores = _scores_with(MECHANISM=0.85, PATTERN=0.70)
        adapter = MockAdapter(
            ClassificationResult(
                scores=scores, confidence=0.85, primary="MECHANISM", reasoning="multi"
            )
        )
        clf, _ = _make_classifier(vault, adapter)
        all_ids = clf.classify_record_lattice(record_id, "test content", "markdown")

        conn = connect(vault / "data" / "cerebra.db")
        try:
            row = conn.execute(
                "SELECT data_json FROM inspector_events WHERE event_type = 'LatticeCommit'"
            ).fetchone()
        finally:
            conn.close()

        assert row is not None
        data = json.loads(row[0])
        assert set(data["sibling_record_ids"]) == set(all_ids)
        assert data["sibling_count"] == len(all_ids)
        assert data["classifier_top_1"] == "MECHANISM"

    def test_below_threshold_returns_empty_list(self, vault: Path) -> None:
        """All categories below 0.65 → no commit, returns []."""
        record_id = _seed_record(vault)
        scores = _low_scores()
        adapter = MockAdapter(
            ClassificationResult(
                scores=scores, confidence=0.30, primary="MECHANISM", reasoning="low"
            )
        )
        clf, _ = _make_classifier(vault, adapter)
        result = clf.classify_record_lattice(record_id, "test content", "markdown", threshold=0.65)
        assert result == []

    def test_classification_failure_returns_empty_list(self, vault: Path) -> None:
        """LLM ClassificationError → returns [], emits ClassificationFailed event."""
        record_id = _seed_record(vault)
        clf, _ = _make_classifier(vault, MockAdapter(raise_error=True))
        result = clf.classify_record_lattice(record_id, "test content", "markdown")
        assert result == []
        assert _count_events(vault, "ClassificationFailed") >= 1

    def test_idempotency_single_commit(self, vault: Path) -> None:
        """Calling classify_record_lattice twice returns same record_id (idempotent)."""
        record_id = _seed_record(vault)
        adapter = MockAdapter(
            ClassificationResult(
                scores=_scores_with(MECHANISM=0.80),
                confidence=0.80,
                primary="MECHANISM",
                reasoning="idem",
            )
        )
        clf, _ = _make_classifier(vault, adapter)
        first = clf.classify_record_lattice(record_id, "test content", "markdown")
        second = clf.classify_record_lattice(record_id, "test content", "markdown")
        assert first == [record_id]
        assert second == [record_id]
