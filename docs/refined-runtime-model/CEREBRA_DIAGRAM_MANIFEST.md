# Cerebra — Diagram Manifest

## Purpose

This manifest lists the individual Mermaid diagram source files for Cerebra.

These `.mmd` files can be rendered individually into SVG, PNG, or PDF.

## Diagram Files

| # | File | Purpose |
|---:|---|---|
| 1 | `01-cerebra-system-architecture.mmd` | Full Cerebra backend spine. |
| 2 | `02-source-ingestion-pipeline.mmd` | How raw sources become memory records. |
| 3 | `03-memory-layer-stack.mmd` | Layered memory model. |
| 4 | `04-hybrid-retrieval-flow.mmd` | Retrieval order and ContextPacket flow. |
| 5 | `05-contextpacket-assembly-flow.mmd` | Agent-ready context assembly. |
| 6 | `06-memory-lifecycle-state-machine.mmd` | Memory lifecycle transitions. |
| 7 | `07-consolidation-engine-flow.mmd` | Memory consolidation flow. |
| 8 | `08-graph-export-lumaweave-bridge.mmd` | Cerebra-to-LumaWeave graph export. |
| 9 | `09-state-governance-map.mmd` | Current state, events, indexes, artifacts. |
| 10 | `10-salience-scoring-components.mmd` | Component-based salience scoring. |

## Rendering Example

```bash
mmdc -i diagrams/01-cerebra-system-architecture.mmd -o docs/assets/diagrams/cerebra-system-architecture.svg
```

## Doctrine

Cerebra diagrams should show memory flow, provenance, retrieval, lifecycle, and graph export.
