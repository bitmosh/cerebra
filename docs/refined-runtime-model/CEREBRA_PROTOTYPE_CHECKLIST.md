# Cerebra — Prototype Checklist

## 1. Purpose

This checklist defines the first thin prototype gate for Cerebra.

The prototype should prove the memory spine before more planning expands the system.

Goal:

```text
ingest three markdown files
create chunks
search them
build a ContextPacket
show retrieval trace
export tiny graph JSON
```

---

## 2. Prototype Non-Goals

Do not build:

```text
full UI
full vector database abstraction
perfect parser
PDF/docx support
complex graph algorithms
automatic consolidation
cloud sync
Policy Scout integration
```

This is a spine test.

---

## 3. Prototype Inputs

Use 3-5 Markdown files.

Suggested files:

```text
CEREBRA_PROJECT_SCOPE.md
CEREBRA_ARCHITECTURE.md
CEREBRA_MEMORY_LAYERS.md
CEREBRA_RETRIEVAL_ARCHITECTURE.md
CEREBRA_CONTEXT_PACKET_PROTOCOL.md
```

---

## 4. Required CLI Commands

Prototype commands:

```bash
cerebra init ./demo-vault
cerebra ingest ./docs
cerebra search "ContextPacket retrieval trace"
cerebra context "Plan Cerebra retrieval implementation"
cerebra export graph --out graph.json
```

---

## 5. Required Data Objects

Prototype must create:

```text
Source
NormalizedDocument
Chunk
MemoryRecord
RetrievalResult
RetrievalTrace
ContextPacket
GraphNode
GraphEdge
```

---

## 6. Required Storage

Prototype storage can be simple.

Minimum:

```text
SQLite database
artifact folder
simple lexical index
simple vector placeholder or lightweight local embedding index
```

If embeddings are not ready, use a placeholder vector abstraction but keep the interface real.

---

## 7. Required Ingestion Behavior

Checklist:

```text
[ ] files discovered
[ ] source IDs generated
[ ] content hashes stored
[ ] markdown detected
[ ] headings parsed
[ ] chunks created
[ ] chunks preserve heading path
[ ] memory records created
[ ] events logged
```

---

## 8. Required Retrieval Behavior

Checklist:

```text
[ ] lexical search returns matches
[ ] vector/semantic placeholder returns candidates or real embeddings
[ ] hybrid fusion combines candidates
[ ] score components are visible
[ ] source provenance included
[ ] retrieval trace stored
```

---

## 9. Required ContextPacket Behavior

Checklist:

```text
[ ] packet ID generated
[ ] task/query stored
[ ] selected memory included
[ ] source provenance included
[ ] token estimate included
[ ] retrieval trace ID included
[ ] JSON rendering works
[ ] plain text rendering works
```

---

## 10. Required Graph Export Behavior

Checklist:

```text
[ ] Source nodes exported
[ ] Document nodes exported
[ ] Chunk nodes exported
[ ] MemoryRecord nodes exported
[ ] CONTAINS edges exported
[ ] DERIVED_FROM edges exported
[ ] project labels included where available
[ ] lifecycle state included
[ ] JSON file written
```

---

## 11. Required Tests

Prototype tests:

```text
[ ] init creates vault
[ ] ingest creates sources
[ ] ingest creates chunks
[ ] no orphan chunks
[ ] search returns expected file
[ ] ContextPacket includes provenance
[ ] graph export contains nodes/edges
```

---

## 12. Success Criteria

Prototype succeeds when:

```text
A developer can ingest the first Cerebra docs, search them, generate a ContextPacket, and export a small graph that LumaWeave could theoretically render.
```

---

## 13. Confidence Update

After prototype:

```text
ingestion confidence should be recalibrated
retrieval confidence should be recalibrated
ContextPacket confidence should be recalibrated
graph export confidence should be recalibrated
```

Prototype results should decide what docs need correction.

---

## 14. Prototype Doctrine

The first prototype is not about polish.

It is about proving Cerebra's spine:

```text
source -> memory -> retrieval -> context -> graph
```
