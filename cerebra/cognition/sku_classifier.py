"""
SKU classifier — assigns D1-D10 SKU addresses to memory records.

Entry points:
  SKUClassifier.classify_record()  — classify one record, write assignment
  SKUClassifier.backfill_null_records()  — sweep all NULL sku_address records

Idempotency: records with matching classifier_version + prompt_version
are skipped. Version change triggers reclassification.

Backfill: processes records in batches (default 50), commits per batch.
On crash, re-query picks up from NULL set — committed batches are safe.

Inspector events emitted here (not in sub-components):
  SKUAssigned, SKUReclassified, ClassificationFailed,
  ClassificationLowConfidence, BackfillStarted, BackfillCompleted
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from cerebra.cognition.llm_adapter import ClassificationError, ClassificationResult, LLMAdapter
from cerebra.cognition.sku import (
    D10Provenance,
    SKUAddress,
    SKUAssignment,
    d9_from_detected_type,
)
from cerebra.cognition.sku_categories import CATEGORY_DESCRIPTIONS, D1Category
from cerebra.inspector.event import make_event
from cerebra.inspector.ndjson_log import NDJSONEventLog
from cerebra.inspector.sqlite_log import SQLiteEventLog
from cerebra.storage.sqlite_store import SQLiteStore

CLASSIFIER_VERSION = "1.0.0"
PROMPT_VERSION = "2.0.0"
SUBCATEGORY_STRATEGY_VERSION = "v1-stub"

# Confidence bands for 4-quadrant calibration reporting
HIGH_CONF_THRESHOLD = 0.5

# D1 anchor threshold: must clear this to be included as the primary category.
# Below this, we still take the highest scorer (no miscellaneous bucket).
D1_ANCHOR_THRESHOLD = 0.4


@dataclass
class BackfillReport:
    records_found: int = 0
    classified: int = 0
    skipped: int = 0
    failed: int = 0
    low_confidence: int = 0
    elapsed_ms: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "records_found": self.records_found,
            "classified": self.classified,
            "skipped": self.skipped,
            "failed": self.failed,
            "low_confidence": self.low_confidence,
            "elapsed_ms": self.elapsed_ms,
        }


class SKUClassifier:
    def __init__(
        self,
        store: SQLiteStore,
        event_log: SQLiteEventLog,
        ndjson: NDJSONEventLog,
        adapter: LLMAdapter,
    ) -> None:
        self._store = store
        self._event_log = event_log
        self._ndjson = ndjson
        self._adapter = adapter

    # ── Public API ────────────────────────────────────────────────────────────

    def classify_record(
        self,
        record_id: str,
        content: str,
        detected_type: str,
    ) -> SKUAssignment | None:
        """
        Classify one record. Returns the assignment, or None on failure.
        Emits all relevant inspector events.
        """
        existing = self._store.get_sku_assignment_for_record(record_id)
        is_reclassification = existing is not None

        if existing and self._is_current(existing):
            return None  # already classified with current versions — skip

        # Classify with retry-once on parse failure
        try:
            result = self._classify_with_retry(content)
        except ClassificationError as e:
            self._emit(
                "ClassificationFailed",
                "sku_classifier",
                f"Classification failed for {record_id}: {e}",
                {"record_id": record_id, "error": str(e)[:400]},
                subject_id=record_id,
            )
            return None

        # Build SKUAddress
        d1 = self._select_d1(result)
        d9 = d9_from_detected_type(detected_type)
        entry_byte = self._store.count_sku_location_occupancy(
            d1.value, 0, 0, 0, 0, 0, d9.value, D10Provenance.OBSERVED.value
        )
        entry_byte = min(entry_byte, 0xFF)
        sku = SKUAddress(
            d1=d1.value,
            d9=d9.value,
            d10=D10Provenance.OBSERVED.value,
            d7=(entry_byte >> 4) & 0xF,
            d8=entry_byte & 0xF,
        )

        now = int(time.time())
        assignment = SKUAssignment(
            assignment_id=f"asgn_{uuid.uuid4().hex[:12]}",
            record_id=record_id,
            sku_address=sku,
            raw_scores=result.scores,
            d1_confidence=result.confidence,
            classifier_version=CLASSIFIER_VERSION,
            prompt_version=PROMPT_VERSION,
            subcategory_strategy_version=SUBCATEGORY_STRATEGY_VERSION,
            model_string=result.model_string,
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            created_at=now,
            pass_count=2,
            raw_scores_json_override=result.raw_scores_json_override,
        )

        # Delete old assignment if reclassifying, then insert new
        if is_reclassification:
            assert existing is not None
            old_sku = existing["sku_address"]
            self._store.delete_sku_assignment_for_record(record_id)
            event_type = "SKUReclassified"
            extra = {"old_sku_address": old_sku}
        else:
            event_type = "SKUAssigned"
            extra = {}

        self._store.insert_sku_assignment(assignment.as_dict())
        self._store.update_record_sku(record_id, sku.to_hex_string(), now)

        # SKUAssigned / SKUReclassified event
        self._emit(
            event_type,
            "sku_classifier",
            f"{event_type}: {record_id} → {sku.to_hex_string()} (D1={d1.name})",
            {
                "record_id": record_id,
                "sku_address": sku.to_hex_string(),
                "d1_category": d1.name,
                "d1_score": result.scores.get(d1.name, 0.0),
                "d1_confidence": result.confidence,
                "prompt_version": PROMPT_VERSION,
                "classifier_version": CLASSIFIER_VERSION,
                "subcategory_strategy_version": SUBCATEGORY_STRATEGY_VERSION,
                "model_string": result.model_string,
                "latency_ms": result.latency_ms,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                **extra,
            },
            subject_id=record_id,
        )

        # Low confidence warning
        if result.confidence < HIGH_CONF_THRESHOLD:
            self._emit(
                "ClassificationLowConfidence",
                "sku_classifier",
                f"Low confidence ({result.confidence:.2f}) for {record_id}",
                {
                    "record_id": record_id,
                    "confidence": result.confidence,
                    "sku_address": sku.to_hex_string(),
                },
                subject_id=record_id,
            )

        return assignment

    def classify_record_lattice(
        self,
        record_id: str,
        content: str,
        detected_type: str,
        threshold: float | None = None,
    ) -> list[str]:
        """
        Classify one record with interpretive lattice multi-commit support.

        If ≥2 categories clear the threshold the primary record is committed
        normally, sibling records are inserted for each additional category,
        and ONE LatticeCommit event is emitted listing all record_ids.

        Returns a list of all record_ids committed (primary first, then
        siblings in descending confidence order). Returns [record_id] on
        single-commit, [] on classification failure.

        The existing classify_record() path is untouched — this method does
        its own write path so the LLM is called exactly once regardless of
        how many siblings are produced.
        """
        from cerebra.cognition._constants import LATTICE_COMMIT_THRESHOLD
        from cerebra.cognition.lattice import (
            LatticeDecision,
            build_sibling_record_id,
            evaluate_lattice,
            new_lineage_id,
        )
        from cerebra.storage.embeddings import queue_for_embedding

        if threshold is None:
            threshold = LATTICE_COMMIT_THRESHOLD

        # Idempotency check — skip if already classified with current versions
        existing = self._store.get_sku_assignment_for_record(record_id)
        is_reclassification = existing is not None
        if existing and self._is_current(existing):
            return [record_id]

        # One LLM call reused for both primary write and lattice decision
        try:
            result = self._classify_with_retry(content)
        except ClassificationError as e:
            self._emit(
                "ClassificationFailed",
                "sku_classifier",
                f"Classification failed for {record_id}: {e}",
                {"record_id": record_id, "error": str(e)[:400]},
                subject_id=record_id,
            )
            return []

        decision: LatticeDecision = evaluate_lattice(result.scores, threshold)

        # Nothing cleared the threshold — treat as unclassifiable
        if not decision.candidates:
            self._emit(
                "ClassificationLowConfidence",
                "sku_classifier",
                f"No category cleared lattice threshold ({threshold}) for {record_id}",
                {
                    "record_id": record_id,
                    "threshold": threshold,
                    "max_score": max(result.scores.values()),
                },
                subject_id=record_id,
            )
            return []

        # ── Write primary record ──────────────────────────────────────────────
        now = int(time.time())
        primary_category = D1Category[decision.top_1_category]
        primary_confidence = decision.top_1_confidence
        d9 = d9_from_detected_type(detected_type)

        entry_byte = self._store.count_sku_location_occupancy(
            primary_category.value, 0, 0, 0, 0, 0, d9.value, D10Provenance.OBSERVED.value
        )
        entry_byte = min(entry_byte, 0xFF)
        primary_sku = SKUAddress(
            d1=primary_category.value,
            d9=d9.value,
            d10=D10Provenance.OBSERVED.value,
            d7=(entry_byte >> 4) & 0xF,
            d8=entry_byte & 0xF,
        )

        primary_assignment = SKUAssignment(
            assignment_id=f"asgn_{uuid.uuid4().hex[:12]}",
            record_id=record_id,
            sku_address=primary_sku,
            raw_scores=result.scores,
            d1_confidence=primary_confidence,
            classifier_version=CLASSIFIER_VERSION,
            prompt_version=PROMPT_VERSION,
            subcategory_strategy_version=SUBCATEGORY_STRATEGY_VERSION,
            model_string=result.model_string,
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            created_at=now,
            pass_count=2,
            raw_scores_json_override=result.raw_scores_json_override,
        )

        if is_reclassification:
            self._store.delete_sku_assignment_for_record(record_id)

        self._store.insert_sku_assignment(primary_assignment.as_dict())
        self._store.update_record_sku(record_id, primary_sku.to_hex_string(), now)

        event_type = "SKUReclassified" if is_reclassification else "SKUAssigned"
        extra: dict[str, object] = (
            {"old_sku_address": existing["sku_address"]} if existing else {}
        )
        self._emit(
            event_type,
            "sku_classifier",
            f"{event_type}: {record_id} → {primary_sku.to_hex_string()} (D1={primary_category.name})",
            {
                "record_id": record_id,
                "sku_address": primary_sku.to_hex_string(),
                "d1_category": primary_category.name,
                "d1_score": result.scores.get(primary_category.name, 0.0),
                "d1_confidence": result.confidence,
                "prompt_version": PROMPT_VERSION,
                "classifier_version": CLASSIFIER_VERSION,
                "subcategory_strategy_version": SUBCATEGORY_STRATEGY_VERSION,
                "model_string": result.model_string,
                "latency_ms": result.latency_ms,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                **extra,
            },
            subject_id=record_id,
        )

        # Single-commit path — no lattice work needed
        if not decision.should_multi_commit:
            return [record_id]

        # ── Multi-commit: build siblings ──────────────────────────────────────
        primary_rec = self._store.get_record(record_id)
        if primary_rec is None:
            return [record_id]

        lineage_id = new_lineage_id()
        self._store.update_record_lattice_membership(record_id, lineage_id, primary_confidence)

        all_record_ids: list[str] = [record_id]
        new_sibling_ids: list[str] = []

        for category_name, confidence in decision.candidates[1:]:
            sibling_id = build_sibling_record_id(record_id, category_name)

            # Idempotent: skip if sibling already exists
            if self._store.get_record(sibling_id) is not None:
                all_record_ids.append(sibling_id)
                continue

            d1_sibling = D1Category[category_name]
            entry_s = self._store.count_sku_location_occupancy(
                d1_sibling.value, 0, 0, 0, 0, 0, d9.value, D10Provenance.OBSERVED.value
            )
            entry_s = min(entry_s, 0xFF)
            sibling_sku = SKUAddress(
                d1=d1_sibling.value,
                d9=d9.value,
                d10=D10Provenance.OBSERVED.value,
                d7=(entry_s >> 4) & 0xF,
                d8=entry_s & 0xF,
            )

            self._store.insert_lattice_record(
                {
                    "record_id": sibling_id,
                    "record_type": primary_rec["record_type"],
                    "source_id": primary_rec["source_id"],
                    "document_id": primary_rec["document_id"],
                    "chunk_id": primary_rec["chunk_id"],
                    "content": primary_rec["content"],
                    "content_hash": primary_rec["content_hash"],
                    "token_estimate": primary_rec["token_estimate"],
                    "sku_address": sibling_sku.to_hex_string(),
                    "sku_assigned_at": now,
                    "lifecycle_state": "active",
                    "created_at": now,
                    "schema_version": 1,
                    "lattice_lineage_id": lineage_id,
                    "is_lattice_member": 1,
                    "lattice_confidence": confidence,
                }
            )

            sibling_assignment = SKUAssignment(
                assignment_id=f"asgn_{uuid.uuid4().hex[:12]}",
                record_id=sibling_id,
                sku_address=sibling_sku,
                raw_scores=result.scores,
                d1_confidence=confidence,
                classifier_version=CLASSIFIER_VERSION,
                prompt_version=PROMPT_VERSION,
                subcategory_strategy_version=SUBCATEGORY_STRATEGY_VERSION,
                model_string=result.model_string,
                latency_ms=result.latency_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                created_at=now,
                pass_count=2,
                raw_scores_json_override=result.raw_scores_json_override,
            )
            self._store.insert_sku_assignment(sibling_assignment.as_dict())

            all_record_ids.append(sibling_id)
            new_sibling_ids.append(sibling_id)

        # Queue new siblings for embedding
        if new_sibling_ids:
            queue_for_embedding(self._store._db_path, new_sibling_ids)

        # ONE LatticeCommit event per chunk
        primary_rec_chunk_id = str(primary_rec["chunk_id"])
        self._emit(
            "LatticeCommit",
            "sku_classifier",
            f"LatticeCommit: {record_id} multi-committed to {len(all_record_ids)} positions",
            {
                "chunk_id": primary_rec_chunk_id,
                "sibling_record_ids": all_record_ids,
                "sibling_count": len(all_record_ids),
                "confidence_distribution": result.scores,
                "threshold_used": threshold,
                "classifier_top_1": decision.top_1_category,
            },
            subject_id=primary_rec_chunk_id,
        )

        return all_record_ids

    def backfill_null_records(
        self,
        batch_size: int = 50,
        dry_run: bool = False,
    ) -> BackfillReport:
        """
        Classify all records with NULL sku_address or version mismatch.
        Commits per batch; re-query resumes from NULL set on crash.
        """
        report = BackfillReport()
        t0 = time.monotonic()

        records = self._store.get_records_needing_classification(CLASSIFIER_VERSION, PROMPT_VERSION)
        report.records_found = len(records)

        if dry_run:
            report.elapsed_ms = int((time.monotonic() - t0) * 1000)
            return report

        self._emit(
            "BackfillStarted",
            "sku_classifier",
            f"SKU backfill starting: {report.records_found} records",
            {"records_found": report.records_found, "batch_size": batch_size},
        )

        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            for rec in batch:
                assignment = self.classify_record(
                    record_id=rec["record_id"],
                    content=rec["content"],
                    detected_type=rec.get("detected_type", "markdown"),
                )
                if assignment is None:
                    # Check if it was a skip (already classified) or failure
                    existing = self._store.get_sku_assignment_for_record(rec["record_id"])
                    if existing and self._is_current(existing):
                        report.skipped += 1
                    else:
                        report.failed += 1
                else:
                    report.classified += 1
                    if assignment.d1_confidence < HIGH_CONF_THRESHOLD:
                        report.low_confidence += 1

        report.elapsed_ms = int((time.monotonic() - t0) * 1000)

        self._emit(
            "BackfillCompleted",
            "sku_classifier",
            f"SKU backfill done: {report.classified} classified, "
            f"{report.failed} failed, {report.low_confidence} low-confidence",
            report.as_dict(),
        )

        return report

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _is_current(self, existing: dict[str, object]) -> bool:
        return (
            existing["classifier_version"] == CLASSIFIER_VERSION
            and existing["prompt_version"] == PROMPT_VERSION
        )

    def _classify_with_retry(self, content: str) -> ClassificationResult:
        """Two-pass classification: Pass 1 quadrant, Pass 2 within-quadrant. Retry each pass once."""
        import json as _json

        # Pass 1: quadrant selection
        for _attempt in range(2):
            try:
                pass1 = self._adapter.classify_quadrant(content)
                break
            except ClassificationError:
                if _attempt == 1:
                    raise

        # Pass 2: within-quadrant (always fires)
        quadrant = pass1.primary
        for _attempt in range(2):
            try:
                pass2 = self._adapter.classify_within_quadrant(content, quadrant)
                break
            except ClassificationError:
                if _attempt == 1:
                    raise

        # Build combined result — pass2 primary is the D1 answer
        combined_scores = _json.dumps({
            "pass1": {
                "scores": pass1.scores,
                "confidence": pass1.confidence,
                "primary_quadrant": pass1.primary,
            },
            "pass2": {
                "quadrant": quadrant,
                "scores": pass2.scores,
                "confidence": pass2.confidence,
                "primary": pass2.primary,
                "reasoning": pass2.reasoning,
            }
        })

        # Return a ClassificationResult using pass2's D1 category
        return ClassificationResult(
            scores=pass2.scores,
            confidence=pass2.confidence,
            primary=pass2.primary,
            reasoning=pass2.reasoning,
            model_string=pass2.model_string,
            latency_ms=(pass1.latency_ms or 0) + (pass2.latency_ms or 0),
            input_tokens=(pass1.input_tokens or 0) + (pass2.input_tokens or 0),
            output_tokens=(pass1.output_tokens or 0) + (pass2.output_tokens or 0),
            raw_scores_json_override=combined_scores,
        )

    def _select_d1(self, result: ClassificationResult) -> D1Category:
        """Select primary D1 category from scores. No miscellaneous bucket."""
        eligible = {k: v for k, v in result.scores.items() if v >= D1_ANCHOR_THRESHOLD}
        if eligible:
            best = max(eligible, key=lambda k: eligible[k])
        else:
            best = max(result.scores, key=lambda k: result.scores[k])
        return D1Category[best]

    def _emit(
        self,
        event_type: str,
        actor: str,
        summary: str,
        data: dict[str, object],
        subject_id: str | None = None,
    ) -> None:
        e = make_event(event_type, actor, summary, data, subject_id=subject_id)
        self._event_log.write(e)
        self._ndjson.write(e)


def _build_classification_prompt(content: str) -> str:
    """
    Build the D1 classification prompt.

    Instructs the model to score all 16 categories 0.0–1.0 and return
    valid JSON. JSON enforcement is via prompt only (response_format is
    dropped by the LiteLLM proxy). Model must return the JSON object
    directly; markdown code fences are stripped by the caller.

    Prompt calibration history:
    v1.0.0: baseline — 12/30 = 40% on qwen3.5:latest
    v1.1.0: added disambiguation section — 10/30 = 33% (worse; 12 empty responses due to prompt length)
    Reverted to v1.0.0. Longer prompts cause empty responses on this model.
    """
    category_lines = "\n".join(f"  {cat.name}: {CATEGORY_DESCRIPTIONS[cat]}" for cat in D1Category)
    return f"""You are a cognitive classifier. Score how well the text fits each of the 16 cognitive categories below on a scale from 0.0 to 1.0. These are cognitive SHAPES — not content topics. Every piece of knowledge expresses one or more of these shapes.

Categories:
{category_lines}

Rules:
- Score ALL 16 categories. No category may be omitted.
- Scores are 0.0–1.0. Multiple high scores are valid if content genuinely spans categories.
- confidence: your overall certainty about the primary classification (0.0–1.0).
- primary: the single highest-scoring category name (exact uppercase name from the list above).
- reasoning: one sentence (no quotation marks inside) citing what drove the primary score.

Return ONLY a JSON object in exactly this shape (no markdown, no code fences, no explanation):
{{
  "scores": {{
    "OBSERVATION": 0.0, "PATTERN": 0.0, "MECHANISM": 0.0, "PHENOMENON": 0.0,
    "TECHNIQUE": 0.0, "DESIGN": 0.0, "CREATION": 0.0, "TOOL": 0.0,
    "PRINCIPLE": 0.0, "JUDGMENT": 0.0, "GOAL": 0.0, "CONSTRAINT": 0.0,
    "EVENT": 0.0, "AGENT": 0.0, "CONTEXT": 0.0, "RELATION": 0.0
  }},
  "confidence": 0.0,
  "primary": "CATEGORY_NAME",
  "reasoning": "one sentence"
}}

Text to classify:
<text>
{content[:2000]}
</text>"""


def _build_pass1_prompt(content: str) -> str:
    """Build the Pass 1 quadrant selection prompt."""
    return f"""You are a classifier. Read the text below and assign it to one of four cognitive quadrants.

EMPIRICAL   — describes how things ARE or WORK: facts, observations, counts, measurements,
              causal processes ("is derived by", "works by", "triggers when"), named entities
GENERATIVE  — describes how things are MADE or DONE: procedures, steps to follow, schemas
              designed, artifacts produced, capabilities that serve a purpose
NORMATIVE   — describes how things SHOULD BE: "must", "should", "do not", "never", "required",
              "is a defect", "non-negotiable", design doctrine, goals, evaluations
RELATIONAL  — describes how things CONNECT: events at specific times, named persons/agents,
              operating environments, dependencies ("enables", "depends on", "X and Y together")

Score all four quadrants 0.0–1.0. Scores may overlap if the text spans quadrants.

Return ONLY valid JSON:
{{"scores": {{"EMPIRICAL": 0.0, "GENERATIVE": 0.0, "NORMATIVE": 0.0, "RELATIONAL": 0.0}},
 "confidence": 0.0, "primary": "QUADRANT_NAME"}}

Text:
<text>
{content[:2000]}
</text>"""


PASS2_PROMPTS: dict[str, str] = {
    "EMPIRICAL": """You are a classifier. This text has been identified as EMPIRICAL — it describes how things
are or work. Now identify which of these four types best fits:

OBSERVATION   — a measurement, count, or recorded state: "39 sources produced", "NULL for
                all 745 records", "confidence=0.9"
PATTERN       — recurring structure across multiple cases: "strategies that work for X tend
                to Y", trends, regularities identified across observations
MECHANISM     — internal causal process: how something works automatically, "is derived by",
                "triggers when X → does Y", state transitions, causal chains with no actor
PHENOMENON    — what something IS: named entity definition, "Cerebra is a [definition]",
                bounded descriptions of what a thing is (not what it does for you)

Key distinctions:
MECHANISM vs OBSERVATION: describes internal causality and process (MECHANISM) vs reports a
  measured state or count (OBSERVATION)? A causal chain is MECHANISM; a number is OBSERVATION.
MECHANISM vs PATTERN: one causal process in one system (MECHANISM) vs recurring regularity
  seen across many instances (PATTERN)?
PHENOMENON vs MECHANISM: defines what something IS (PHENOMENON) vs describes how it WORKS (MECHANISM)?

Score all four 0.0–1.0.
Return ONLY valid JSON:
{{"scores": {{"OBSERVATION": 0.0, "PATTERN": 0.0, "MECHANISM": 0.0, "PHENOMENON": 0.0}},
 "confidence": 0.0, "primary": "CATEGORY_NAME", "reasoning": "one sentence"}}

Text:
<text>
{content}
</text>""",
    "GENERATIVE": """You are a classifier. This text has been identified as GENERATIVE — it describes how things
are made or done. Now identify which of these four types best fits:

TECHNIQUE   — procedure: steps a person or system FOLLOWS to accomplish something, how-to
              instructions, "to X: do A, then B, then C", methods with an active actor
DESIGN      — structure: intentional architectural choices already made, schemas, "the table
              stores X, Y, Z", scope decisions ("Phase 2 assigns X, stubs Y")
CREATION    — artifact: something produced and placed somewhere, "vendored into", deliverables,
              outputs, works produced
TOOL        — capability: what an instrument does FOR the user; interface description;
              "Clutch maps signal to action", capability-interface language

Key distinctions:
TECHNIQUE vs DESIGN: steps to follow (TECHNIQUE) vs structure already decided (DESIGN)?
  "To create X, do Y" = TECHNIQUE. "The table has columns A, B, C" = DESIGN.
TOOL vs MECHANISM: what the instrument provides (TOOL) vs how its internals work (MECHANISM)?
  "Maps X to Y" = TOOL. "Rules fire in priority order, first match wins" = MECHANISM.
DESIGN vs CREATION: the architectural choice (DESIGN) vs the artifact produced (CREATION)?

Score all four 0.0–1.0.
Return ONLY valid JSON:
{{"scores": {{"TECHNIQUE": 0.0, "DESIGN": 0.0, "CREATION": 0.0, "TOOL": 0.0}},
 "confidence": 0.0, "primary": "CATEGORY_NAME", "reasoning": "one sentence"}}

Text:
<text>
{content}
</text>""",
    "NORMATIVE": """You are a classifier. This text has been identified as NORMATIVE — it describes how things
should be. Now identify which of these four types best fits:

PRINCIPLE   — behavioral standard or design doctrine: "must [do X]", "should", "is required",
              "non-negotiable", "opacity is a defect", normative rules about how systems
              SHOULD work
JUDGMENT    — evaluation or appraisal: weighing tradeoffs, assessing quality, "X is better
              than Y because...", critique of a design decision
GOAL        — desired state: "desired outcome", "the target is", success criteria, what's
              being pursued
CONSTRAINT  — hard prohibition or limit: "do not", "never", "forbidden", "must not", "do not
              patch one by one", explicit outer walls

Key distinction:
PRINCIPLE vs CONSTRAINT: behavioral standard — what SHOULD happen (PRINCIPLE) vs hard
  prohibition — what MUST NOT happen (CONSTRAINT)?
  "Must emit events" = PRINCIPLE (positive requirement).
  "Do not assist with..." = CONSTRAINT (explicit prohibition).
  "Non-negotiable" alone is a PRINCIPLE marker, not CONSTRAINT.
PRINCIPLE vs GOAL: normative doctrine (PRINCIPLE) vs desired outcome (GOAL)?
  "Desired outcome for Phase 2" = GOAL. "Inspector events are non-negotiable" = PRINCIPLE.

Score all four 0.0–1.0.
Return ONLY valid JSON:
{{"scores": {{"PRINCIPLE": 0.0, "JUDGMENT": 0.0, "GOAL": 0.0, "CONSTRAINT": 0.0}},
 "confidence": 0.0, "primary": "CATEGORY_NAME", "reasoning": "one sentence"}}

Text:
<text>
{content}
</text>""",
    "RELATIONAL": """You are a classifier. This text has been identified as RELATIONAL — it describes how things
connect. Now identify which of these four types best fits:

EVENT    — something that happened at a specific moment: "Phase 0 complete on 2026-06-04",
           "88 tests passed", time-situated occurrences
AGENT    — a person, organization, or system with intent and role: "bitmosh is the sole
           developer of Cerebra", roles and responsibilities
CONTEXT  — the environment or setting something operates within: vault directories, system
           conditions, operating environments, "the vault contains..."
RELATION — connection between things: dependencies, enablement, "LumaWeave and Cerebra",
           "X makes Y possible", "X enables Z"

Key distinction:
CONTEXT vs DESIGN: existing environment described (CONTEXT) vs intentional structural
  choice made (DESIGN)? "The vault directory contains X, Y" = CONTEXT. "The vault was
  designed with separate data and event directories" = DESIGN.
EVENT vs OBSERVATION: time-situated occurrence (EVENT) vs measured count (OBSERVATION)?
  "Phase 0 complete on [date]" = EVENT. "745 chunks produced" = OBSERVATION.

Score all four 0.0–1.0.
Return ONLY valid JSON:
{{"scores": {{"EVENT": 0.0, "AGENT": 0.0, "CONTEXT": 0.0, "RELATION": 0.0}},
 "confidence": 0.0, "primary": "CATEGORY_NAME", "reasoning": "one sentence"}}

Text:
<text>
{content}
</text>""",
}


def _build_pass2_prompt(content: str, quadrant: str) -> str:
    """Build the Pass 2 within-quadrant classification prompt."""
    template = PASS2_PROMPTS.get(quadrant)
    if template is None:
        raise ValueError(f"Unknown quadrant: {quadrant!r}. Must be one of {list(PASS2_PROMPTS)}")
    return template.format(content=content[:2000])
