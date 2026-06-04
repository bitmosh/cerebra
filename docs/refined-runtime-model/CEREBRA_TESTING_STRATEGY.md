# Cerebra — Testing Strategy

## 1. Purpose

This document defines the testing strategy for Cerebra.

Cerebra stores and retrieves user memory. Testing must verify correctness, provenance, retrieval quality, lifecycle behavior, and failure handling.

The goal is not just code coverage.

The goal is memory trust.

---

## 2. Testing Doctrine

Tests should verify:

```text
source provenance
schema validity
retrieval traceability
lifecycle rules
ContextPacket integrity
index freshness
graph export correctness
failure recovery
```

Do not only test happy paths.

Do not only test final retrieval results.

Test the intermediate records.

---

## 3. Test Categories

Initial test categories:

```text
vault tests
source registry tests
type detection tests
parser adapter tests
normalization tests
chunking tests
memory record tests
storage tests
index tests
retrieval tests
salience tests
ContextPacket tests
lifecycle tests
consolidation tests
graph tests
CLI tests
failure tests
```

---

## 4. Vault Tests

Verify:

- vault initializes
- init is idempotent
- config exists
- database exists
- schema version recorded
- artifact directories created

---

## 5. Source Registry Tests

Verify:

- source registered
- source ID generated
- content hash stored
- duplicate source detected
- modified source detected
- unsupported file recorded
- source status transitions work

---

## 6. Type Detection Tests

Fixtures:

```text
.md
.txt
.json
.yaml
.csv
.py
.ts
.unknown
binary stub
```

Verify:

- detected type
- confidence
- adapter selection
- fallback behavior
- unsupported behavior

---

## 7. Parser Adapter Tests

For each adapter, verify:

```text
parse success
parse confidence
metadata extraction
warnings/errors
normalized document output
source provenance
```

Initial adapters:

```text
text
markdown
json
yaml
csv
code
```

---

## 8. Normalization Tests

Verify:

- headings preserved
- code blocks preserved
- links preserved where possible
- whitespace normalized
- sections created
- metadata normalized
- confidence stored

---

## 9. Chunking Tests

Verify:

- chunks have IDs
- chunks link to source/document
- heading path preserved
- token estimate exists
- chunker version stored
- no orphan chunks
- code blocks not split badly where avoidable
- tables handled conservatively

---

## 10. Memory Record Tests

Verify:

- source chunk records created
- summaries link to support
- records have lifecycle state
- records have confidence
- records have schema version
- records serialize to JSON
- provenance chain exists

---

## 11. Storage Tests

Verify:

- records persist
- records reload
- migrations run
- events persist
- artifact store writes/reads
- database handles missing records clearly
- transaction rollback works

---

## 12. Index Tests

Verify:

- lexical index builds
- vector index builds
- metadata index works
- index freshness tracked
- stale index warnings appear
- tombstoned records excluded
- archive behavior respected

---

## 13. Retrieval Tests

Test retrieval modes:

```text
exact lexical lookup
semantic lookup
hybrid lookup
metadata-filtered lookup
project-scoped lookup
archive-aware lookup
```

Verify:

- result IDs
- score components
- selected/excluded candidates
- retrieval trace
- lifecycle filtering
- source provenance

---

## 14. Salience Tests

Verify component behavior:

```text
project relevance boost
source authority boost
pinned memory boost
low-confidence penalty
tombstone exclusion
archive lowering
recency behavior
exact lexical match boost
semantic similarity contribution
```

Salience tests should inspect components, not only final score.

---

## 15. ContextPacket Tests

Verify:

- packet ID generated
- task/query stored
- selected memory included
- provenance included
- token estimate included
- retrieval trace ID included
- JSON rendering works
- plain text rendering works
- uncertainties included when present
- excluded candidates recorded where enabled

---

## 16. Lifecycle Tests

Verify:

```text
active records retrieve
archived records lower or card-only retrieval
tombstoned records excluded
deleted markers prevent stale references
restore works
lifecycle events created
re-ingestion respects tombstones
```

---

## 17. Consolidation Tests

Verify:

- duplicate detection
- summary creation
- summary support links
- archive retrieval card creation
- relationship creation
- consolidation record creation
- source records not deleted
- human-review boundaries enforced

---

## 18. Graph Tests

Verify:

- source-document-chunk-memory provenance graph
- project membership edges
- summary support edges
- duplicate edges
- contradiction edges
- lifecycle filtering
- graph expansion bounds
- export JSON schema
- tombstoned node exclusion

---

## 19. CLI Tests

Test:

```bash
cerebra init ./vault
cerebra ingest ./fixtures/docs
cerebra search "query"
cerebra context "query"
cerebra consolidate
cerebra archive mem_123
cerebra tombstone mem_123
cerebra export graph
```

Verify:

- exit codes
- human-readable output
- JSON output where available
- no silent failures

---

## 20. Failure Tests

Simulate:

```text
parser failure
unsupported file
corrupt JSON
database unavailable
vector index failure
embedding failure
stale index
consolidation failure
graph export failure
```

Expected behavior:

```text
store error
continue where safe
preserve source record
degrade retrieval gracefully
report uncertainty
do not lose memory silently
```

---

## 21. Quality Fixtures

Create fixture vaults:

```text
small markdown project
mixed text/code project
contradictory notes project
duplicate notes project
archive/tombstone project
graph relationship project
```

These fixtures should become reusable regression tests.

---

## 22. Testing Doctrine

Cerebra should be tested like a memory system, not just a search tool.

Every important output should answer:

```text
Where did this come from?
Why was it selected?
What supports it?
What state is it in?
What changed it?
```
