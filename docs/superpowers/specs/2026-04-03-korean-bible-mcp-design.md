# Korean Bible MCP Server Design

## Summary

Build a local-first MCP server for Korean Bible study and sermon preparation. The first release focuses on high-quality Korean Bible text retrieval with hybrid search across keyword, semantic, and contextual signals. The server must run fully locally on a personal computer, avoid commercial datasets, and remain compatible with MCP clients such as Claude Desktop, Cursor, and Windsurf.

## Product Goal

The v1 goal is a Korean Bible MCP server that can:

- search the full Korean Bible text with hybrid retrieval
- return exact passages directly by reference
- expand surrounding context around a verse or passage
- suggest semantically related passages
- summarize a selected passage for study preparation

The v1 goal is not full sermon generation, and it is not a complete biblical people and events research platform yet.

## Constraints

- Bible text will come from a user-provided local database
- only open data may be used for metadata enrichment
- the system must support complete local execution
- the primary deployment target is a single personal computer
- no commercial datasets or hosted retrieval dependencies are allowed

## Users And Usage Context

Primary users are individual pastors, teachers, and Bible-study leaders using an MCP-capable AI client locally. They need to ask natural-language questions such as:

- "믿음과 두려움이 함께 나타나는 본문 찾아줘"
- "마태복음 5장 팔복 문맥까지 보여줘"
- "로마서 8장과 비슷한 위로 본문 추천해줘"

The server should return passages that are readable as study units rather than isolated vector hits.

## Scope

### In Scope For V1

- Korean Bible full-text ingestion from a user-supplied database
- normalized verse storage
- passage chunk generation for semantic and context retrieval
- SQLite FTS5 keyword search
- local embedding-based semantic retrieval
- context expansion around search hits
- hybrid result scoring and deduplication
- MCP tools for search, direct passage lookup, context expansion, related-passage suggestion, and passage summary
- metadata scaffolding for future people, places, and events linking

### Out Of Scope For V1

- full people and events knowledge graph experience
- automatic sermon manuscript generation
- multi-user deployment and server-side tenancy
- commercial or hosted Bible datasets
- mandatory reranking with a large local LLM

## Data Sources

### Core Bible Text

The core Bible text comes from a user-provided local database. The server will validate the required schema on startup or during indexing.

### Open Metadata Sources

Use open data only, with normalization into local tables:

- STEPBible data for people and proper-name relationships
- Theographic Bible Metadata for people, places, passages, and biblical chronology signals
- OpenBible geocoding data for place coordinates and verse linkage
- optional Wikidata alias enrichment for Korean and English name variants

These metadata sources are not the center of v1 runtime behavior. They serve as a future-facing enrichment layer and can appear in search result metadata when available.

## Architecture

The system will start as a single Python MCP server with clear internal module boundaries:

- `ingest`: reads the user Bible database and metadata sources, validates schema, and writes normalized records
- `index`: builds text chunks, FTS indexes, embedding jobs, and vector indexes
- `query`: executes hybrid retrieval, context assembly, deduplication, and response shaping
- `tools`: exposes MCP tools with stable input and output schemas

This is a single-process architecture for v1 because the target deployment is a single personal machine and installation simplicity matters more than throughput. The code should still preserve boundaries so indexing can be split from runtime later if needed.

## Storage Design

### SQLite

SQLite is the primary relational store. It contains:

- normalized verse records
- chunk metadata
- metadata entities such as people, events, and places
- entity aliases and entity-to-verse links
- FTS5 virtual tables for keyword retrieval

SQLite is preferred because it is local, stable, simple to distribute, and strong enough for v1 retrieval metadata and exact passage lookup.

### Vector Index

Semantic retrieval uses a local vector index, stored separately from SQLite. FAISS is the preferred v1 backend because it is mature, local-first, and simple to integrate from Python.

SQLite stores metadata about embeddings, while FAISS stores the actual vectors.

## Data Model

### `verses`

Stores the normalized verse text.

Representative fields:

- `id`
- `translation`
- `book`
- `book_order`
- `chapter`
- `verse`
- `reference`
- `testament`
- `text`

### `passage_chunks`

Stores context-aware text units for semantic retrieval and result display.

Representative fields:

- `chunk_id`
- `start_ref`
- `end_ref`
- `book`
- `chapter_range`
- `text`
- `token_count`
- `chunk_strategy`

Chunk generation should prefer paragraph or pericope-like units when available. If that structure is not available from the source, fallback logic should group adjacent verses into bounded multi-verse chunks.

### `verses_fts`

An SQLite FTS5 virtual table for keyword and phrase retrieval over verse text and optionally normalized text variants.

### `chunk_embeddings`

Stores embedding metadata.

Representative fields:

- `chunk_id`
- `model_name`
- `embedding_version`
- `updated_at`

The vector payload itself is stored in FAISS rather than in SQLite.

### Entity Tables

Future-facing enrichment tables:

- `people`
- `events`
- `places`
- `entity_aliases`
- `entity_verse_links`

These tables exist in v1 primarily to support related metadata in search results and to prevent schema redesign later.

## Search Pipeline

### 1. Query Normalization

Normalize Korean whitespace and punctuation, resolve Bible book aliases, parse direct references where possible, and apply minimal stopword handling. The normalization step must preserve important theological terms and should avoid aggressive stemming that damages Korean meaning.

### 2. Keyword Retrieval

Run FTS5 retrieval across verse text and chunk text. This stage handles exact wording, phrase matches, distinctive nouns, and strong lexical anchors.

### 3. Semantic Retrieval

Embed the query with a fully local embedding model and retrieve nearby chunk vectors from FAISS. This stage handles topic-level and meaning-level similarity even when wording differs.

### 4. Context Assembly

Take top chunk candidates and expand them into readable passage units. Expansion rules should prefer paragraph or pericope boundaries, and otherwise expand by a bounded verse window around the hit.

### 5. Hybrid Scoring

Combine:

- FTS lexical relevance
- vector similarity
- context quality adjustments

The scoring rule should favor exact lexical matches when they are strong, while still allowing semantic matches to surface when explicit wording differs.

### 6. Deduplication And Explanation

Merge overlapping results into a single passage when needed. Each result should include explanation fields such as:

- matched terms
- semantic reason
- context summary
- related entities when available

This is important because MCP users need traceable results, not only ranked IDs.

## Local Model Strategy

The system must support fully local execution by default.

- embeddings must be generated locally
- retrieval must work offline after setup
- semantic search should degrade gracefully if the embedding model is missing or temporarily unavailable

The initial model choice should prioritize acceptable Korean semantic quality with manageable local runtime cost. The exact model can remain configurable in server settings.

Optional local reranking may be added later, but it is not a hard dependency for v1.

## MCP Tool Surface

### `search_bible`

Primary hybrid search tool.

Inputs:

- natural-language or keyword query
- optional translation filter
- optional result limit

Outputs:

- `reference`
- `passage_text`
- `score`
- `match_reasons`
- `related_entities`

### `lookup_passage`

Direct Bible passage retrieval by explicit reference.

Inputs:

- verse or passage reference such as `창세기 12:1-3`

Outputs:

- exact normalized Bible text for that passage

This tool intentionally bypasses search ranking when the user already knows the reference.

### `expand_context`

Expands the context around a verse or result hit.

Inputs:

- verse reference or passage reference
- optional window or boundary mode

Outputs:

- expanded passage text with clear start and end references

### `suggest_related_passages`

Finds passages semantically related to a selected verse or passage.

Inputs:

- reference or source text
- optional limit

Outputs:

- ranked related passages with similarity explanations

### `summarize_passage`

Summarizes a passage for study preparation.

Inputs:

- reference or passage text

Outputs:

- concise summary
- topic keywords
- repeated motifs or contrasts when detectable

Initial implementation should remain conservative and may use rule-based or lightweight local summarization methods.

### `search_entities`

A supporting metadata query for v1.

Inputs:

- people, place, or event name

Outputs:

- matching entities
- alias matches
- linked verse references when available

This is included in v1 mainly as scaffolding for later entity-first workflows.

## Setup And Runtime Flow

### Initial Setup

1. User provides the local Bible database path.
2. The indexing command validates the source schema.
3. The system writes normalized verses and chunks into SQLite.
4. The system builds FTS5 indexes.
5. The system generates chunk embeddings locally.
6. The system writes the FAISS vector index.

### Runtime

- the MCP server starts quickly if the local indexes already exist
- if indexes are missing, tool calls should fail with precise guidance rather than vague runtime errors
- if semantic components fail, the server should continue to serve keyword-based search where possible

## Error Handling

The system should fail early and specifically.

- if the Bible DB path is missing, return a configuration error with the required path setting
- if the Bible DB schema is incompatible, return a schema-validation error with expected columns or tables
- if indexes are missing, return an indexing-required error with the exact command to run
- if the local embedding model is missing, return a model-setup error and optionally fall back to keyword-only search
- if a query is too broad or ambiguous, return refinement hints rather than silently poor results

Error messages should be action-oriented and suitable for MCP clients, where short, structured failure messages are easier to work with than stack traces.

## Quality Strategy

### Retrieval Principles

- search unit for ranking is primarily the chunk
- display unit for the user is a readable context passage
- exact lexical hits should generally outrank weak semantic hits
- overlapping results should collapse into coherent passages

### Evaluation

Maintain a golden query set of representative Korean Bible-study questions. This set should include:

- exact keyword searches
- theme searches
- indirect semantic searches
- direct passage lookups
- context-expansion cases

This evaluation set is required because retrieval quality can regress quietly when chunking or score weights change.

## Testing Strategy

### Normalization Tests

- Korean query normalization
- Bible book alias resolution
- verse and passage parsing

### Indexing Tests

- verse ingestion correctness
- chunk-generation correctness
- FTS index population
- embedding metadata and FAISS alignment

### Retrieval Tests

- keyword retrieval expectations
- semantic retrieval expectations
- context assembly correctness
- hybrid ranking sanity checks

### MCP Integration Tests

- tool input validation
- tool response schema validation
- error response stability

## Future Expansion Path

After v1 retrieval is stable, the next layer can expand into:

- people-first study workflows
- event extraction and timeline views
- theme bundle generation for sermon preparation
- passage comparison and clustering
- stronger local reranking and summarization

The current schema and module boundaries should make those additions incremental rather than requiring a rewrite.

## Recommended Implementation Direction

Implement v1 as a Python MCP server backed by SQLite, FTS5, FAISS, and a configurable local Korean-capable embedding model. Keep metadata enrichment in the schema from the start, but prioritize the retrieval quality of Korean Bible text search above everything else.

## Acceptance Criteria For V1

The design is considered satisfied when:

- a user can point the server at a local Korean Bible database and build indexes locally
- `search_bible` returns relevant passages using keyword, semantic, and context-aware signals
- `lookup_passage` returns exact text for direct references
- `expand_context` returns readable surrounding passage text
- `suggest_related_passages` returns plausible semantically related passages
- the server works from MCP clients on a personal machine without hosted dependencies
- failures are explicit and actionable rather than opaque
