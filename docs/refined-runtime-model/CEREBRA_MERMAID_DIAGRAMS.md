# Cerebra — Mermaid Diagrams

## 1. Cerebra System Architecture

```mermaid
flowchart LR
  sources[Source Bank<br/>files / docs / code / exports] --> registry[Source Registry]
  registry --> router[Ingestion Router]
  router --> adapters[Parser Adapters]
  adapters --> normalize[Normalization Layer]
  normalize --> chunker[Chunker]
  chunker --> records[Memory Record Builder]

  records --> store[(Memory Store<br/>SQLite + artifacts)]
  records --> lexical[(Lexical Index)]
  records --> vector[(Vector Index)]
  records --> graph[(Graph Store)]

  lexical --> retrieval[Retrieval Engine]
  vector --> retrieval
  graph --> retrieval
  store --> retrieval

  retrieval --> context[ContextPacket Builder]
  retrieval --> trace[(Retrieval Trace)]

  store --> consolidation[Consolidation Engine]
  consolidation --> lifecycle[Lifecycle Manager]
  consolidation --> graph
  lifecycle --> store

  graph --> export[Graph Exporter]
  export --> luma[LumaWeave]

  context --> agents[Agents / Tools]
```

---

## 2. Source Ingestion Pipeline

```mermaid
flowchart TD
  discover[Source Discovered] --> register[Source Registered]
  register --> detect[Type Detected]
  detect --> route[Adapter Selected]
  route --> parse[Source Parsed]
  parse --> normalize[Content Normalized]
  normalize --> metadata[Metadata Extracted]
  metadata --> sections[Document Sections Created]
  sections --> chunks[Chunks Created]
  chunks --> records[Memory Records Built]
  records --> indexes[Indexes Updated]
  records --> relations[Relationships Suggested]
  indexes --> event[Ingestion Event Logged]
  relations --> event
```

---

## 3. Memory Layer Stack

```mermaid
flowchart BT
  L8[L8 Archive / Tombstone Layer]
  L7[L7 Consolidated Long Memory]
  L6[L6 ContextPackets]
  L5[L5 Relationship Graph]
  L4[L4 Derived Summaries]
  L3[L3 Memory Records]
  L2[L2 Chunks]
  L1[L1 Normalized Documents]
  L0[L0 Source Artifacts]

  L0 --> L1
  L1 --> L2
  L2 --> L3
  L3 --> L4
  L3 --> L5
  L4 --> L7
  L5 --> L6
  L7 --> L6
  L3 --> L8
  L4 --> L8
```

---

## 4. Hybrid Retrieval Flow

```mermaid
flowchart LR
  query[Query / Task] --> planner[Query Planner]
  planner --> lexical[Lexical Retrieval]
  planner --> vector[Vector Retrieval]
  planner --> metadata[Metadata Filters]

  lexical --> fusion[Hybrid Fusion]
  vector --> fusion
  metadata --> fusion

  fusion --> graph[Graph Expansion]
  graph --> summaries[Summary / Community Retrieval]
  summaries --> salience[Salience Scoring]
  salience --> rerank[Reranking]
  rerank --> budget[Context Budget Allocation]
  budget --> packet[ContextPacket]
  budget --> trace[(Retrieval Trace)]
```

---

## 5. ContextPacket Assembly Flow

```mermaid
flowchart TD
  task[Task / Agent Need] --> plan[Retrieval Plan]
  plan --> candidates[Candidate Memories]
  candidates --> score[Score + Rerank]
  score --> budget[Token Budget Allocation]
  budget --> selected[Selected Memory]
  budget --> summaries[Source Summaries]
  budget --> graph[Graph Context]
  budget --> uncertain[Uncertainties]
  budget --> excluded[Excluded Candidates]

  selected --> packet[ContextPacket]
  summaries --> packet
  graph --> packet
  uncertain --> packet
  excluded --> packet
  packet --> render[Plain Text + JSON Rendering]
  packet --> store[(Stored Packet + Trace)]
```

---

## 6. Memory Lifecycle State Machine

```mermaid
stateDiagram-v2
  [*] --> active
  active --> warm
  warm --> cold
  cold --> archived
  archived --> warm: restore
  archived --> tombstoned
  active --> tombstoned
  warm --> tombstoned
  cold --> tombstoned
  tombstoned --> active: explicit restore
  tombstoned --> deleted: explicit purge
  active --> quarantined
  quarantined --> active: review approved
  quarantined --> tombstoned: review rejected
  deleted --> [*]
```

---

## 7. Consolidation Engine Flow

```mermaid
flowchart TD
  trigger[Consolidation Trigger] --> select[Candidate Selection]
  select --> cluster[Grouping / Clustering]
  cluster --> duplicates[Duplicate Detection]
  cluster --> summarize[Summary Generation]
  cluster --> contradictions[Contradiction Checks]
  cluster --> stale[Staleness Checks]

  duplicates --> relationships[Relationship Updates]
  summarize --> relationships
  contradictions --> relationships
  stale --> lifecycle[Lifecycle Recommendations]

  relationships --> salience[Salience Updates]
  lifecycle --> record[Consolidation Record]
  salience --> record
  record --> review{Human Review Needed?}
  review -->|yes| pending[Pending Review]
  review -->|no| write[Write Outputs]
```

---

## 8. Graph Export / LumaWeave Bridge

```mermaid
flowchart LR
  store[(Cerebra Memory Store)] --> nodes[Graph Nodes]
  store --> edges[Graph Edges]
  store --> clusters[Clusters / Summaries]
  store --> lifecycle[Lifecycle State]

  nodes --> export[Graph Export JSON]
  edges --> export
  clusters --> export
  lifecycle --> export

  export --> luma[LumaWeave]
  luma --> views[Graph Views<br/>memory maps / timelines / clusters]
```

---

## 9. State Governance Map

```mermaid
flowchart TD
  subgraph current[Current State]
    sources[Sources]
    docs[Documents]
    chunks[Chunks]
    records[Memory Records]
    rels[Relationships]
    lifecycle[Lifecycle State]
  end

  subgraph events[Event History]
    eventlog[(Memory Event Log)]
  end

  subgraph indexes[Indexes]
    lexical[Lexical Index]
    vector[Vector Index]
    graphindex[Graph Index]
    metadata[Metadata Index]
  end

  subgraph artifacts[Artifacts]
    raw[Source Refs / Raw Artifacts]
    normalized[Normalized Docs]
    reports[Summaries / Exports]
  end

  current --> eventlog
  current --> indexes
  current --> artifacts
  indexes --> retrieval[Retrieval Engine]
  eventlog --> trace[Traceability]
```

---

## 10. Salience Scoring Components

```mermaid
flowchart LR
  semantic[Semantic Similarity] --> salience[Salience Score]
  lexical[Lexical Match] --> salience
  project[Project Relevance] --> salience
  authority[Source Authority] --> salience
  recency[Recency] --> salience
  access[Access Frequency] --> salience
  pin[User Pin] --> salience
  graph[Relationship Centrality] --> salience
  confidence[Confidence] --> salience
  lifecycle[Lifecycle State] --> salience
  task[Task Relevance] --> salience
  penalties[Contradiction / Staleness / Sensitivity Penalties] --> salience

  salience --> ranking[Retrieval Ranking]
  salience --> context[ContextPacket Selection]
```
