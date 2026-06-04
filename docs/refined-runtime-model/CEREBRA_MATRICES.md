# Cerebra — Matrices and Reference Tables

## 1. Purpose

This document collects practical matrices for Cerebra implementation, testing, and future visual aids.

Matrices help keep behavior clear without turning the system into vague prose.

These are summaries, not replacements for schema-governed implementation.

---

## 2. Source Type → Adapter Matrix

| Source Type | Examples | MVP Adapter | Confidence Strategy | Notes |
|---|---|---|---|---|
| Plain text | `.txt`, logs, notes | `text` | high if readable text | Preserve line boundaries where useful. |
| Markdown | `.md`, docs | `markdown` | high | Preserve headings, code blocks, links. |
| JSON | `.json` | `json` | high if valid JSON | Keep structure and summarize keys. |
| YAML | `.yaml`, `.yml` | `yaml` | high if valid YAML | Useful for configs and registries. |
| CSV | `.csv` | `csv` | moderate-high | Store schema/columns and row summaries. |
| Code | `.py`, `.ts`, `.rs`, `.js` | `code` | moderate | MVP can use lightweight symbol hints. |
| PDF | `.pdf` | later `pdf_text` | variable | Defer unless local parser is easy. |
| Office docs | `.docx`, `.odt` | later | variable | Defer for MVP. |
| Chat export | `.json`, `.txt`, `.md` | later specialized | variable | Important later for conversation memory. |
| Policy Scout report | `.md`, `.json` | later specialized | high if structured | Optional source, not core dependency. |
| Binary/unknown | unknown | `generic_binary_stub` | low | Register metadata, do not hallucinate contents. |

---

## 3. Memory Layer → Storage / Retrieval Matrix

| Layer | Stored As | Retrieval Role | Lifecycle Behavior |
|---|---|---|---|
| L0 Source Artifacts | file refs, hashes, metadata | provenance lookup | never altered silently |
| L1 Normalized Documents | artifact store + SQLite metadata | section/source lookup | can be regenerated |
| L2 Chunks | SQLite + artifact text | lexical/vector candidates | can be archived/cold |
| L3 Memory Records | SQLite records | primary retrieval object | active/warm/cold/archive/tombstone |
| L4 Derived Summaries | SQLite + artifact text | summary retrieval | high value if source-linked |
| L5 Relationship Graph | SQLite graph tables | graph expansion | lifecycle-aware edges |
| L6 ContextPackets | JSON/artifact + SQLite | agent context inspection | store/summarize/archive |
| L7 Consolidated Long Memory | SQLite records | high-salience retrieval | user-review for sensitive claims |
| L8 Archive/Tombstone | archive manifest + tombstone records | explicit/archive-aware retrieval | prevents accidental resurrection |

---

## 4. Retrieval Mode Matrix

| Mode | Best For | Uses | MVP? |
|---|---|---|---|
| `exact_lookup` | file names, symbols, IDs | lexical + metadata | yes |
| `hybrid_search` | general search | lexical + vector fusion | yes |
| `project_scoped` | active project work | metadata + salience | yes |
| `graph_expand` | related context | graph neighbors | basic |
| `archive_search` | old/cold material | archive cards + explicit retrieval | basic |
| `global_summary` | broad overview | summaries/community summaries | later |
| `drift_like` | local + global mixed reasoning | local search + community summaries | later |
| `context_refresh` | updating agent state | recent ContextPackets + retrieval trace | later |

---

## 5. Lifecycle State Matrix

| State | Normal Retrieval | ContextPacket Eligible | Graph Visible | Restore? | Notes |
|---|---|---|---|---|---|
| `active` | yes | yes | yes | n/a | Current useful memory. |
| `warm` | yes | yes | yes | n/a | Useful but less central. |
| `cold` | lowered | maybe | yes | n/a | Low-access but not useless. |
| `archived` | retrieval card / explicit | usually no | graph stub | yes | Compressed/cold storage. |
| `tombstoned` | no | no | marker only | explicit only | Blocks resurrection. |
| `deleted` | no | no | no or deletion marker | no | Physical purge where possible. |
| `quarantined` | no | no | review marker | after review | Untrusted/poisoned/low-confidence. |

---

## 6. Salience Component Matrix

| Component | Boosts When | Penalizes When | MVP |
|---|---|---|---|
| semantic similarity | meaning matches task | low semantic match | yes |
| lexical match | exact term/symbol match | no exact anchor | yes |
| project relevance | same active project | different project | yes |
| source authority | canonical/user-authored | speculative/generated | yes |
| recency | current project phase | old stale detail | yes |
| confidence | extraction/source high-confidence | low confidence | yes |
| lifecycle state | active/warm | archived/tombstoned/quarantined | yes |
| user pin | user marks important | unpinned | yes |
| relationship centrality | connected to important graph | isolated | later |
| task relevance | matches task type | irrelevant to task | later |
| contradiction penalty | no contradiction | contradicted/superseded | later/basic |
| sensitivity penalty | safe for agent context | sensitive/secret-adjacent | later/basic |

---

## 7. ContextPacket Section Matrix

| Section | Purpose | Required MVP |
|---|---|---|
| task/query | explains why packet exists | yes |
| selected memory | main agent context | yes |
| source provenance | supports trust | yes |
| score components | explains selection | yes |
| summaries | compact high-level context | yes/basic |
| graph context | relationship hints | basic |
| uncertainties | prevents false certainty | yes |
| excluded candidates | explains omissions | optional/basic |
| token budget | context management | yes |
| retrieval trace | inspectability | yes |

---

## 8. Consolidation Action Matrix

| Action | Auto OK? | Human Review? | Notes |
|---|---|---|---|
| link exact duplicates | yes | no | Preserve provenance. |
| create document summary | yes | no | Must link support. |
| create topic summary | yes | optional | Confidence-aware. |
| create archive retrieval card | yes | optional | Do not delete sources. |
| mark stale | maybe | for high-salience records | Prefer recommendation first. |
| resolve contradiction | no | yes | Do not silently pick winner. |
| tombstone memory | no | yes | User/system explicit only. |
| delete memory | no | yes | Explicit purge only. |
| promote durable fact | maybe | for sensitive/personal claims | Must link source support. |

---

## 9. MVP Confidence Matrix

| Area | Current Confidence | Main Risk | Prototype Evidence Needed |
|---|---:|---|---|
| Source registry | 94% | path/hash edge cases | ingest + re-ingest fixtures |
| Text/Markdown ingestion | 92% | chunk boundaries | markdown fixture tests |
| JSON/YAML/CSV ingestion | 86–90% | structure flattening quality | mixed structured fixtures |
| Code ingestion | 78–84% | symbol extraction depth | keep MVP lightweight |
| Hybrid retrieval | 90–93% | ranking quality | compare lexical/vector/fusion |
| ContextPacket protocol | 92–94% | token budgeting details | generated packet inspection |
| Lifecycle/tombstone | 86–90% | restore/delete semantics | lifecycle tests |
| Consolidation v0 | 82–87% | summary quality/overclaiming | support-linked summaries |
| Graph export | 88–91% | schema stability | tiny LumaWeave-ready export |

---

## 10. Matrix Doctrine

Matrices should help agents implement consistently.

If behavior changes, update the relevant matrix and source architecture doc.
