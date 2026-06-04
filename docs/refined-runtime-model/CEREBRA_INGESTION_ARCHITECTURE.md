# Cerebra — Ingestion Architecture

## 1. Purpose

This document defines Cerebra's source ingestion architecture.

Ingestion is the front door of Cerebra.

It determines how raw user data becomes structured, retrievable, graph-ready memory.

Cerebra should ingest many source types, but it should not pretend that every source can be perfectly understood. Every adapter should preserve provenance, confidence, and uncertainty.

---

## 2. Core Doctrine

Cerebra ingestion should be:

```text
source-grounded
adapter-based
schema-governed
provenance-preserving
confidence-aware
idempotent
incremental
local-first
failure-tolerant
```

Ingestion should never create memory with no source trail.

---

## 3. Ingestion Flow

```text
Source Discovered
  -> Source Registered
  -> Type Detected
  -> Adapter Selected
  -> Source Parsed
  -> Content Normalized
  -> Metadata Extracted
  -> Document Sections Created
  -> Chunks Created
  -> Memory Records Built
  -> Indexes Updated
  -> Relationships Suggested
  -> Ingestion Event Logged
```

---

## 4. Source Discovery

Sources may be discovered through:

```text
manual file path
folder ingestion
watch directory
import manifest
CLI command
local API
future app integration
future Policy Scout report adapter
```

Initial MVP should support:

```bash
cerebra ingest ./docs
cerebra ingest ./project
cerebra ingest ./file.md
```

---

## 5. Source Registry

Every source should be registered before parsing.

Source registry fields:

```text
source_id
source_uri
source_path
source_type_guess
content_hash
size_bytes
created_at
modified_at
ingested_at
parser_status
parser_adapter
parser_confidence
schema_version
```

The source registry prevents duplicate ingestion and supports incremental updates.

---

## 6. Type Detection

Type detection should combine:

```text
file extension
MIME guess
magic bytes where available
content sniffing
user override
adapter availability
```

Detection output:

```json
{
  "source_id": "src_123",
  "detected_type": "markdown",
  "confidence": 0.96,
  "signals": {
    "extension": ".md",
    "mime": "text/markdown",
    "content_sniff": "markdown_headings"
  }
}
```

Low-confidence detection should route to safe fallback parsing.

---

## 7. Adapter Selection

The ingestion router selects an adapter.

Initial adapters:

```text
text
markdown
json
yaml
csv
code
pdf_text
generic_binary_stub
```

Later adapters:

```text
docx
odt
html
email
chat_export
notebook
audio_transcript
image_metadata
archive_zip
policy_scout_report
```

Adapter selection should produce:

```text
adapter_name
adapter_version
selection_confidence
fallback_adapter
reason
```

---

## 8. Parser Adapter Contract

Every parser adapter should implement a common contract.

Input:

```text
source_id
source_path
source_metadata
adapter_options
```

Output:

```text
ParseResult
NormalizedDocument candidate
metadata
warnings
errors
confidence
```

Adapter output should not directly write memory records.

Adapters parse; the ingestion pipeline writes.

---

## 9. ParseResult Model

Example:

```json
{
  "parse_id": "parse_123",
  "source_id": "src_123",
  "adapter": "markdown",
  "adapter_version": "0.1.0",
  "success": true,
  "confidence": 0.95,
  "normalized_document_id": "doc_123",
  "warnings": [],
  "errors": [],
  "extracted_metadata": {
    "title": "Cerebra Architecture",
    "headings_count": 12
  }
}
```

---

## 10. NormalizedDocument Model

Normalized documents are stable intermediate representations.

Example:

```json
{
  "document_id": "doc_123",
  "source_id": "src_123",
  "document_type": "markdown",
  "title": "Cerebra Architecture",
  "content": "...",
  "sections": [],
  "metadata": {},
  "normalization_confidence": 0.94,
  "schema_version": 1
}
```

Normalized documents should preserve:

```text
source order
headings
section boundaries
code blocks
tables where possible
links/references
offset hints where possible
```

---

## 11. Metadata Extraction

Metadata extraction should be adapter-specific and normalized.

Common metadata:

```text
title
author
created_at
modified_at
language
source_type
project
tags
headings
file_extension
file_size
content_hash
```

Code metadata:

```text
language
imports
symbols
classes
functions
comments
module path
```

Document metadata:

```text
title
headings
sections
frontmatter
links
tables
```

---

## 12. Chunking

Chunking should happen after normalization.

Chunking strategies:

```text
heading-based
paragraph-based
semantic
code-symbol
table-aware
sliding-window fallback
```

Each chunk must preserve:

```text
chunk_id
source_id
document_id
position
heading_path
content
token_estimate
chunk_strategy
confidence
```

---

## 13. Chunking Rules

General rules:

1. Prefer natural document boundaries.
2. Avoid chunks with no provenance.
3. Keep code symbols intact where possible.
4. Keep headings with their section content.
5. Keep tables coherent where possible.
6. Use sliding windows only as fallback.
7. Track chunker version.
8. Track token estimates.

---

## 14. Memory Record Creation

Chunks become memory records.

Memory records may include:

```text
source_chunk
document_summary
entity
relationship
project_note
decision
task
report_summary
```

The record builder should not over-extract from weak sources.

If confidence is low, create a conservative chunk record and defer deeper interpretation.

---

## 15. Relationship Suggestion

Ingestion may suggest graph relationships.

Examples:

```text
source belongs_to project
chunk mentions entity
document references file
code imports module
summary derived_from chunks
report relates_to project
```

Relationship suggestions should have confidence.

Do not make low-confidence relationships central by default.

---

## 16. Idempotency

Ingestion should avoid duplicate records.

Use:

```text
source path
content hash
adapter version
normalizer version
chunker version
schema version
```

If content hash and processing versions match, skip reprocessing unless forced.

---

## 17. Incremental Updates

When a source changes:

```text
detect hash change
mark old normalized document stale
re-parse source
re-chunk
compare chunk hashes
reuse unchanged records where possible
update indexes
log SourceChanged event
```

Do not blindly duplicate all chunks.

---

## 18. Error Handling

Ingestion should fail gracefully.

Examples:

```text
unsupported file -> register source with unsupported status
parser failure -> store ParseFailed event
partial extraction -> store warnings and partial result
binary file -> create metadata-only stub
large file -> defer or chunk streaming
```

Failures should be visible.

---

## 19. Confidence and Uncertainty

Every ingestion stage should preserve confidence.

Stages:

```text
type detection confidence
adapter selection confidence
parse confidence
normalization confidence
chunk confidence
extraction confidence
relationship confidence
```

Uncertainty should affect retrieval and consolidation.

---

## 20. Local-First Ingestion

Ingestion should not upload user files by default.

Cloud parsing or external APIs should be optional adapters.

Default MVP behavior:

```text
local parsing
local storage
local indexing
no network required except optional model/embedding setup
```

---

## 21. Policy Scout as Optional Source

Policy Scout may later provide source material:

```text
Scout Reports
audit event summaries
security findings
package review reports
```

Cerebra should ingest these through an adapter like any other structured source.

Policy Scout is not required for core Cerebra ingestion.

---

## 22. MVP Ingestion Scope

Cerebra v0.1 should support:

```text
text
markdown
json
yaml
csv
code files
folder ingestion
source registry
hash-based dedupe
basic chunking
basic memory records
basic metadata extraction
```

PDF/docx/odt can be later unless easy local parsing is available.

---

## 23. Testing Requirements

Ingestion tests should cover:

```text
source registration
file type detection
adapter selection
markdown parsing
text parsing
json parsing
code parsing
chunking
metadata extraction
hash dedupe
incremental re-ingestion
unsupported file handling
parse failure handling
provenance preservation
```

---

## 24. Ingestion Doctrine

Cerebra should be generous in what it can accept, but strict in what it claims to understand.

When in doubt:

```text
preserve source
extract conservatively
record uncertainty
keep provenance
avoid hallucinated structure
```
