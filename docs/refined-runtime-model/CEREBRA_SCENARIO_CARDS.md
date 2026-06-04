# Cerebra — Scenario Cards

## 1. Purpose

Scenario cards provide compact implementation examples for Cerebra.

They are useful for:

```text
README examples
test fixture design
agent handoff
prototype planning
future visual cards
```

---

## 2. Scenario Template

```text
Scenario:
  <name>

Input:
  <source/query/action>

Expected Flow:
  <major steps>

Expected Output:
  <records/results/events>

Important Checks:
  <what must be true>
```

---

## 3. Scenario — Ingest Markdown Project Docs

```text
Scenario:
  Ingest Markdown Project Docs

Input:
  cerebra ingest ./docs

Expected Flow:
  discover files
  register sources
  detect markdown
  parse headings/code blocks
  normalize document
  create chunks
  create memory records
  update indexes
  log ingestion events

Expected Output:
  source records
  normalized documents
  chunks with heading paths
  source_chunk memory records
  lexical/vector index entries

Important Checks:
  chunks preserve source provenance
  headings are not lost
  code blocks are preserved
```

---

## 4. Scenario — Re-Ingest Unchanged File

```text
Scenario:
  Re-Ingest Unchanged File

Input:
  cerebra ingest ./docs/CEREBRA_ARCHITECTURE.md

Expected Flow:
  compute hash
  detect existing unchanged source
  skip reprocessing or mark unchanged

Expected Output:
  no duplicate memory records
  event noting unchanged source

Important Checks:
  idempotency works
  no duplicate chunks
```

---

## 5. Scenario — Search Exact Symbol

```text
Scenario:
  Search Exact Symbol

Input:
  cerebra search "ContextPacket"

Expected Flow:
  query planner detects exact term
  lexical retrieval finds direct matches
  vector retrieval finds related context
  hybrid fusion ranks exact anchors high
  retrieval trace is stored

Expected Output:
  memory records mentioning ContextPacket
  related protocol docs
  score components showing lexical boost

Important Checks:
  exact term is not lost in vector-only retrieval
```

---

## 6. Scenario — Search Conceptual Query

```text
Scenario:
  Search Conceptual Query

Input:
  cerebra search "how does memory cool down over time?"

Expected Flow:
  vector retrieval finds lifecycle docs
  lexical retrieval may find archive/cold/tombstone terms
  salience boosts Cerebra lifecycle records
  hybrid results return memory lifecycle content

Expected Output:
  lifecycle records
  archive/tombstone references
  source provenance

Important Checks:
  semantic query works even without exact phrase
```

---

## 7. Scenario — Build ContextPacket for Agent

```text
Scenario:
  Build ContextPacket

Input:
  cerebra context "Plan implementation of ingestion adapters" --project Cerebra

Expected Flow:
  project-scoped retrieval
  hybrid search
  salience scoring
  token budget allocation
  selected memory assembly
  provenance included
  retrieval trace stored

Expected Output:
  ContextPacket JSON
  plain text rendering
  selected memory records
  retrieval trace ID

Important Checks:
  agent receives source-grounded context
  user can inspect why items were selected
```

---

## 8. Scenario — Archive Low-Access Cluster

```text
Scenario:
  Archive Low-Access Cluster

Input:
  cerebra archive --topic "old planning notes"

Expected Flow:
  candidate selection
  create archive summary
  create retrieval card
  create graph stub
  update lifecycle states
  log lifecycle events

Expected Output:
  archive package/record
  retrieval card
  archived memory lowered in normal retrieval

Important Checks:
  memory is not deleted
  retrieval card remains searchable
```

---

## 9. Scenario — Tombstone False Memory

```text
Scenario:
  Tombstone False Memory

Input:
  cerebra tombstone mem_123 --reason "incorrect generated claim"

Expected Flow:
  mark record tombstoned
  remove from normal retrieval
  create tombstone marker
  update indexes
  log tombstone event

Expected Output:
  tombstone record
  memory excluded from ContextPackets

Important Checks:
  re-ingestion does not resurrect the same false claim silently
```

---

## 10. Scenario — Consolidate Duplicate Notes

```text
Scenario:
  Consolidate Duplicate Notes

Input:
  cerebra consolidate --project Cerebra

Expected Flow:
  select candidate records
  detect duplicate/near-duplicate notes
  link duplicates
  choose canonical/supporting records
  create summary if useful
  recommend archive for redundant records

Expected Output:
  duplicate edges
  consolidation record
  optional summary
  lifecycle recommendations

Important Checks:
  sources are not deleted
  duplicate handling is traceable
```

---

## 11. Scenario — Export Graph to LumaWeave

```text
Scenario:
  Export Graph

Input:
  cerebra export graph --project Cerebra --out cerebra_graph.json

Expected Flow:
  collect nodes
  collect edges
  include provenance
  include lifecycle state
  include confidence
  write graph JSON

Expected Output:
  LumaWeave-ready graph JSON

Important Checks:
  graph export does not own visualization
  tombstoned nodes are excluded or marked according to export mode
```

---

## 12. Scenario — Ingest Policy Scout Report Later

```text
Scenario:
  Optional Policy Scout Report Ingestion

Input:
  cerebra ingest ./reports/scout_report_123.md

Expected Flow:
  detect structured report
  parse as report source
  create report_summary memory
  link to project if known
  index as source-grounded memory

Expected Output:
  report memory record
  source provenance
  optional findings entities

Important Checks:
  Policy Scout remains optional source material
  report does not become Cerebra governance logic
```

---

## 13. Scenario Doctrine

If a scenario is important enough to document, it should eventually become a test fixture.
