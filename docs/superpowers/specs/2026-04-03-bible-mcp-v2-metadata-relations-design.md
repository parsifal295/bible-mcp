# Bible MCP V2 Metadata And Direct Relations Design

## Summary

Extend the current local-first Korean Bible MCP server with a real metadata ingest pipeline and direct entity relation lookup. V2 keeps the existing Bible-text-first retrieval features intact while adding structured entity data for people, places, aliases, verse links, and direct relationships.

This version does not attempt a full biblical knowledge graph or multi-hop reasoning. It focuses on making direct relation queries dependable and locally reproducible.

## Product Goal

V2 adds a second data layer on top of the existing verse and passage index:

- ingest structured metadata fixtures into the app database during indexing
- support large internal fixtures as the initial metadata source
- resolve people and place names from Korean and English aliases
- answer direct relation questions such as:
  - "야곱의 아들"
  - "다윗의 아버지"
  - "예수의 제자"
- keep the system ready for future adapters for STEPBible, Theographic, and OpenBible sources

## Scope

### In Scope

- metadata fixture files stored in the repository
- normalized metadata import into SQLite
- new relationship table for direct entity-to-entity relations
- richer entity search over display names, aliases, and slugs
- MCP relation lookup for direct relations only
- tests covering ingest, lookup, ambiguity handling, and MCP responses

### Out Of Scope

- automatic download of external metadata datasets
- multi-hop graph traversal such as "야곱의 손자"
- pathfinding or lineage chain reasoning
- geospatial search and map workflows
- chronology and event timeline research workflows

## Design Principles

- Keep v1 Bible retrieval behavior unchanged.
- Introduce metadata through a separate ingest path instead of overloading verse import.
- Use repository fixtures first, but shape them as the internal normalized format for future adapters.
- Prefer explicit and narrow MCP tools over a single overly-smart natural-language graph tool.
- Return deterministic, inspectable results. Never guess when name resolution is ambiguous.

## Current State

The current codebase already has placeholder entity tables and an `EntityService`, but the runtime database contains no metadata rows. The existing entity search behavior only supports exact matches against `people.display_name` and `entity_aliases.alias`. There is no relationship table, no metadata import step, and no direct relation MCP tool.

V2 treats those existing tables as scaffolding and turns them into a real supported data path.

## Architecture

V2 keeps the current single-process architecture:

- `ingest`: loads structured metadata fixtures and writes normalized rows
- `db`: owns schema additions for relationships and indexes
- `services`: resolves entities and reads direct relations
- `mcp_server`: exposes new tools with stable response shapes

The runtime still uses SQLite for relational data and FAISS for semantic passage retrieval. Metadata lookup stays entirely in SQLite.

## Data Sources

### V2 Source Strategy

V2 uses repository-local fixture files as the authoritative metadata source. These fixtures are versioned with the codebase and make the ingest pipeline reproducible in development, tests, and runtime builds.

### Future Source Strategy

The fixture schema becomes the internal canonical format for later adapters. Future importers can normalize external sources into the same structure without changing the runtime service layer.

Planned future adapters:

- STEPBible for people and relationship signals
- Theographic for people, places, passages, and chronology
- OpenBible for place coordinates and verse linkage

## Fixture Layout

Fixture files live under:

- `src/bible_mcp/metadata/fixtures/people.json`
- `src/bible_mcp/metadata/fixtures/places.json`
- `src/bible_mcp/metadata/fixtures/events.json`
- `src/bible_mcp/metadata/fixtures/aliases.json`
- `src/bible_mcp/metadata/fixtures/entity_verse_links.json`
- `src/bible_mcp/metadata/fixtures/relationships.json`

Each file contains normalized records ready for import. The files should be large enough to support meaningful relation lookup coverage, especially for major biblical figures and common direct relation questions.

## SQLite Data Model

### Existing Tables To Populate

V2 populates these existing tables:

- `people`
- `places`
- `events`
- `entity_aliases`
- `entity_verse_links`

### New Table: `entity_relationships`

This table stores normalized direct relationships between entities.

Representative fields:

- `id`
- `source_type`
- `source_slug`
- `relation_type`
- `target_type`
- `target_slug`
- `is_primary`
- `note`

The table stores directed edges. If two-way lookup is required, the importer may insert both directions explicitly when appropriate.

### Recommended Relation Types For V2

- `father`
- `mother`
- `son`
- `daughter`
- `child`
- `spouse`
- `brother`
- `sister`
- `disciple_of`

The importer should reject unknown relation types so the fixture set stays internally consistent.

## Metadata Import Pipeline

### Entry Point

`bible-mcp index` continues to run verse import and passage indexing, then runs a new metadata import step.

High-level flow:

1. validate source Bible DB
2. ensure schema
3. import verses
4. import metadata fixtures
5. build chunks
6. rebuild FTS
7. rebuild embeddings and FAISS

### Import Rules

- Metadata import is independent from Bible text import.
- Import order should make foreign references resolvable:
  1. people, places, events
  2. aliases
  3. entity_verse_links
  4. relationships
- Import is idempotent for repeated indexing runs.
- Existing metadata rows should be replaced during a rebuild so runtime state matches fixture state exactly.
- Invalid references in aliases, verse links, or relationships should fail indexing with actionable errors.

### Validation Rules

The metadata importer validates:

- required fields are present
- slugs are unique per entity type
- aliases reference existing entities
- relationship endpoints exist
- entity verse references point to valid Bible references
- relation types are in the allowed set

## Service Layer

### Entity Search

The current `EntityService` expands from exact match only to deterministic lookup over:

- `display_name`
- `alias`
- `slug`

Search behavior:

- exact display-name matches rank first
- exact alias matches rank next
- exact slug matches rank next
- prefix and substring matching may be added if they remain deterministic and are tested
- entity type filtering is optional
- ambiguous results are returned as candidates, not auto-resolved

### Relation Lookup Service

Add a dedicated service responsible for:

- resolving the source entity from `query`
- reading direct relations from `entity_relationships`
- optionally filtering by `relation_type`
- returning related target entities with readable display data

This service does not perform multi-hop traversal in V2.

## MCP Tool Surface

### `search_entities`

Purpose:

- resolve names, aliases, or slugs to candidate entities

Inputs:

- `query` required
- `entity_type` optional
- `limit` optional

Outputs:

- `results`
  - `entity_type`
  - `slug`
  - `display_name`
  - `description`
  - `matched_by`

### `get_entity_relations`

Purpose:

- return direct relations for one resolved entity

Inputs:

- `query` required
- `relation_type` optional
- `entity_type` optional
- `direction` optional, default `outgoing`
- `limit` optional

Outputs:

- `resolved_entity`
  - `entity_type`
  - `slug`
  - `display_name`
- `matches`
  - candidate list when the query is ambiguous
- `relations`
  - `relation_type`
  - `entity_type`
  - `slug`
  - `display_name`
  - `description`

### Tool Behavior Rules

- If no entity matches, return an empty `relations` list and empty `matches`.
- If multiple entities match and no single deterministic resolution exists, return the candidate list and no relation rows.
- If `relation_type` is omitted, return all direct outgoing relations grouped only by row structure, not by nested JSON complexity.
- Unknown relation types should produce validation errors at the tool boundary.

## Query Handling

V2 relation lookup is intentionally constrained.

Supported patterns:

- entity only: return all direct outgoing relations
- entity + direct relation type: return matching direct relations

Examples:

- `query="야곱", relation_type="child"`
- `query="다윗", relation_type="father", direction="incoming"` if the edge model requires it
- `query="예수", relation_type="disciple_of"` is likely empty, while inverse modeling can instead expose `query="예수", relation_type="teacher_of"` in a later version

V2 does not try to infer relation words from arbitrary Korean sentences inside the service layer. MCP clients can still pass structured arguments, and future versions may add a natural-language relation parser on top of this tool.

## Fixture Coverage Expectations

V2 fixture coverage should be broad enough for realistic direct lookup use.

Minimum practical expectations:

- major patriarchs and matriarchs
- key kings and prophets
- Jesus, his family, and the twelve disciples
- major place names referenced in common study questions
- enough alias coverage for Korean and common English spellings

The fixture set should be treated as large and expandable, but still curated and testable.

## Testing Strategy

V2 uses TDD and adds test coverage in four layers.

### Fixture And Import Tests

- fixture loader reads valid files
- invalid fixture rows fail with clear messages
- metadata import populates all entity tables
- repeated imports remain idempotent

### Service Tests

- entity search finds by Korean display name
- entity search finds by English alias
- ambiguous queries return candidate lists
- direct relation lookup returns expected rows for core examples

### MCP Tool Tests

- tool registration includes the new relation tool when metadata is available
- `search_entities` returns enriched result shape
- `get_entity_relations` returns deterministic payloads

### Regression Tests

Add direct relation regression coverage for:

- `야곱` -> children
- `다윗` -> father
- `예수` -> disciples, using the relation direction chosen by the final edge model

## Backward Compatibility

- Existing Bible text search, passage lookup, context expansion, related passage suggestion, and summarization must continue to work unchanged.
- Metadata lookup remains optional only in the sense that the schema can exist without future adapters. In V2, the repository fixture path should provide actual rows in normal builds.
- Search result shapes should stay backward compatible unless new optional metadata fields are added.

## Risks And Mitigations

### Risk: Ambiguous Name Resolution

Mitigation:

- never auto-pick between multiple candidates without deterministic ranking
- return candidate lists in tool responses
- encourage tool chaining through slug/type identifiers

### Risk: Fixture Drift

Mitigation:

- keep fixtures normalized and versioned in-repo
- validate all references during indexing
- add regression tests for core entity questions

### Risk: Overreaching Into Knowledge Graph Work

Mitigation:

- keep V2 strictly on direct relations
- exclude multi-hop traversal and geospatial workflows from this implementation

## Success Criteria

V2 is complete when:

- indexing imports repository metadata fixtures into the app database
- entity-related tables contain non-zero rows after indexing
- `search_entities` resolves common Korean and English aliases
- `get_entity_relations` answers direct relation lookups for core examples
- ambiguous names return candidates instead of silent guesses
- existing v1 Bible retrieval features still pass their test suite

