# Bible MCP Theographic Ingest Design

## Summary

Replace the current tiny repo-managed metadata slice with a reproducible Theographic-backed ingest pipeline that keeps `index` local and deterministic while preserving curated Korean usability for core people and places.

The design separates remote fetch from local indexing:

- `fetch-theographic` downloads a pinned Theographic snapshot into a versioned local cache
- `sync-theographic` normalizes that snapshot into the current SQLite metadata schema
- `index` remains offline and only consumes already-synced metadata

This design does not attempt a full multilingual biblical knowledge graph. It introduces a larger English-first metadata base plus a curated Korean overlay for `people` and `places`.

## Goals

- ingest substantially larger metadata from Theographic
- keep runtime metadata lookup reproducible and local
- preserve current Korean UX for core people and places
- keep existing MCP tool contracts stable
- avoid mixing network activity into `bible-mcp index`

## Non-Goals

- automatic Korean coverage for the entire imported graph
- replacing all local curated metadata with machine-generated Korean names
- multi-hop graph reasoning
- event chronology workflows beyond direct event import
- changing the current MCP response shapes

## Why This Exists

The current bundled metadata is intentionally tiny. It proves the path end to end, but it does not provide meaningful entity coverage. Earlier design work named `STEPBible`, `Theographic`, and `OpenBible` as future adapters, but no external adapter exists in the current codebase.

Theographic is the first adapter because it already publishes:

- `people.json`
- `places.json`
- `events.json`
- `verses.json`

Those files are sufficient to populate the current internal schema:

- `people`
- `places`
- `events`
- `entity_aliases`
- `entity_verse_links`
- `entity_relationships`

## Source Strategy

### Selected Source

Use `robertrouse/theographic-bible-metadata` as the primary external metadata source.

The current public repository exposes JSON exports suitable for relational normalization. The project documentation states that the JSON files are the preferred source format. The dataset is licensed under CC BY-SA 4.0 and that provenance must be preserved in the local cache manifest and user-facing docs.

### Files Required For V1 Adapter

- `json/people.json`
- `json/places.json`
- `json/events.json`
- `json/verses.json`

These four files are enough for the initial adapter. Other Theographic tables such as `books`, `chapters`, `peopleGroups`, or `easton` are not required for the first milestone.

## High-Level Architecture

The metadata pipeline becomes a three-stage flow:

1. `fetch-theographic`
   Download a pinned raw snapshot into a local versioned vendor directory.
2. `sync-theographic`
   Read the raw snapshot, normalize it, merge curated overlay rules, validate references, and write the normalized metadata into the app database.
3. `index`
   Continue to import verses, rebuild chunks and FTS, and write embeddings, but never perform network operations.

This keeps remote state, normalization logic, and indexing concerns separate. Fetch failures do not corrupt the app database. Sync failures do not partially mutate metadata. Index remains reproducible.

## Files And Responsibilities

- `src/bible_mcp/vendor/theographic_fetcher.py`
  Fetch pinned raw Theographic files and write a manifest.
- `src/bible_mcp/vendor/theographic_normalizer.py`
  Convert raw Theographic JSON into the internal normalized metadata bundle.
- `src/bible_mcp/vendor/metadata_overlay.py`
  Apply canonical slug remaps and curated Korean overrides for `people` and `places`.
- `src/bible_mcp/ingest/metadata_importer.py`
  Import any normalized `MetadataBundle` into SQLite atomically.
- `src/bible_mcp/cli.py`
  Add `fetch-theographic` and `sync-theographic` commands and keep `index` offline.
- `src/bible_mcp/metadata/models.py`
  Continue to define the normalized bundle contract shared by fixture and Theographic sources.
- `docs/` and `README.md`
  Document fetch, sync, provenance, and offline indexing behavior.

## Local Snapshot Layout

Raw Theographic snapshots live outside `src/` and are treated as generated vendor data.

Directory layout:

- `data/vendor/theographic/<commit>/raw/people.json`
- `data/vendor/theographic/<commit>/raw/places.json`
- `data/vendor/theographic/<commit>/raw/events.json`
- `data/vendor/theographic/<commit>/raw/verses.json`
- `data/vendor/theographic/<commit>/manifest.json`
- optional: `data/vendor/theographic/<commit>/normalized/*.json`

The `<commit>` directory name is the exact pinned source ref used for the snapshot.

## Manifest Contract

Each fetched snapshot writes a manifest containing:

- `source_repo`
- `source_ref`
- `resolved_commit`
- `license`
- `fetched_at`
- `files`
- per-file `sha256`
- per-file source URL

The manifest is the source of truth for reproducibility and operator debugging.

## CLI Contract

### `bible-mcp fetch-theographic`

Responsibilities:

- resolve a configured or explicit Theographic ref
- download required JSON files
- compute hashes
- write the manifest
- preserve the last valid snapshot if a new fetch fails

This command is the only networked metadata command.

### `bible-mcp sync-theographic`

Responsibilities:

- locate a fetched snapshot
- normalize Theographic records into the internal metadata bundle
- apply overlay rules
- validate canonical Bible references against the current verse DB
- import the normalized metadata atomically

This command is local-only. It may fail if the app DB does not yet contain verses needed for reference validation.

### `bible-mcp index`

Responsibilities:

- validate source Bible DB
- ensure schema
- import verses
- require previously-synced metadata
- rebuild chunks, FTS, and embeddings

`index` must never call `fetch-theographic`.

## Normalized Data Model

The internal normalized contract remains the current metadata bundle:

- `people`
- `places`
- `events`
- `aliases`
- `entity_verse_links`
- `relationships`

This avoids service-layer churn. Runtime tools and service code continue to speak the same internal format.

## Theographic Normalization Rules

### People

Read from `people.json`.

Mapping rules:

- `slug`:
  default to Theographic `fields.slug`
- `display_name`:
  prefer `fields.displayTitle`, fallback to `fields.name`
- `description`:
  use a shortened first paragraph from dictionary-style text when available

Alias inputs may include:

- `fields.name`
- `fields.displayTitle` when different
- other explicit name fields if present and stable enough for exact matching

Relationship inputs may include:

- `father`
- `mother`
- `children`
- `siblings`
- `partners`

### Places

Read from `places.json`.

Mapping rules:

- `slug`:
  default to Theographic `fields.slug`
- `display_name`:
  prefer `fields.displayTitle`, fallback to `fields.esvName`, then `fields.kjvName`
- `latitude`:
  prefer normalized numeric `fields.latitude`
- `longitude`:
  prefer normalized numeric `fields.longitude`

Alias inputs may include:

- `fields.displayTitle`
- `fields.esvName`
- `fields.kjvName`
- additional stable location labels when present

### Events

Read from `events.json`.

Mapping rules:

- `slug`:
  derive from a stable event identifier when present, otherwise from a normalized title plus Theographic event ID
- `display_name`:
  `fields.title`
- `description`:
  prefer `fields.notes`, otherwise `None`

The first milestone does not provide Korean overlay coverage for general events.

### Verse Links

Read entity-to-verse links indirectly through `verses.json` and entity verse arrays.

Theographic verse records identify verses using `osisRef`, such as `Gen.1.1`. The current runtime expects canonical references such as `Genesis 1:1`. The normalizer therefore converts OSIS references to runtime references before import.

Rules:

- build a `verse_id -> osisRef` lookup from `verses.json`
- convert OSIS book abbreviations to canonical book names
- convert `Book.Chapter.Verse` into `Book Chapter:Verse`
- deduplicate links per `(entity_type, entity_slug, reference)`
- cap imported links per entity to keep the dataset bounded

Initial cap:

- `entity_verse_links` limit = `20` rows per entity

This cap should be configurable, but the initial shipped default is `20`.

### Relationships

Normalize direct people relationships only in the first milestone.

Generated edge rules:

- `father` -> `father`
- `mother` -> `mother`
- `children` -> always `child`, and additionally `son` or `daughter` when child gender is known
- `partners` -> `spouse`
- `siblings` -> `brother` or `sister` when sibling gender is known

The importer writes directed edges. Symmetric relationships are materialized explicitly rather than inferred at query time.

## Overlay Strategy

Theographic is the large English-first base. Curated local metadata becomes an overlay layer.

Overlay responsibilities:

- preserve stable canonical slugs for core entities already exposed to users
- preserve current Korean aliases for core `people` and `places`
- preserve curated Korean display names and descriptions where they already exist
- detect and fail on ambiguous canonical remaps

### Canonical Slug Policy

For core entities already established in the local dataset, keep current canonical slugs.

Representative examples:

- `abraham_58` -> `abraham`
- `isaac_616` -> `isaac`
- `jacob_683` -> `jacob`
- `jesus_904` -> `jesus`
- `jerusalem_636` -> `jerusalem`
- `bethlehem_218` -> `bethlehem`

For imported entities without an overlay remap, use the Theographic slug as the canonical slug.

This keeps existing user-facing identifiers stable for high-value entities without forcing a hand-written slug map for the entire imported graph.

### Korean Coverage Policy

First milestone Korean overlay coverage applies to:

- `people`
- `places`

It does not broadly apply to `events`.

This means:

- core people and places keep Korean-first usability
- newly imported long-tail entities remain English-first until a later Korean alias expansion phase

### Overlay Data Shape

The overlay should be represented in a structured file, not hidden in code branches.

Required overlay abilities:

- map external source slug -> canonical slug
- override `display_name`
- override `description`
- append aliases

The overlay format must be explicit enough to detect collisions during sync.

## Backward Compatibility

The following behaviors must remain stable:

- `search_entities()` without `entity_type` still defaults to `people`
- current MCP tool names remain unchanged
- relation lookup remains direct and deterministic
- passage lookup continues to use canonical references resolved against the `verses` table
- `index` remains a local command once prerequisites exist

## Validation Rules

### Fetch Validation

Fetch must fail if:

- GitHub request fails
- required files are missing
- resolved commit cannot be determined
- downloaded content hash does not match the manifest being written

Failed fetch attempts must not delete the last valid snapshot.

### Sync Validation

Sync must fail if:

- manifest is missing
- required raw files are missing
- Theographic record structure is not in the expected `id` + `fields` shape
- OSIS references cannot be converted
- canonical references do not resolve through the current `PassageService`
- overlay remaps cause multiple external entities to collapse into one canonical slug incorrectly
- relationship targets are missing after normalization

### Import Validation

Import remains atomic and uses the existing bundle-validation approach:

- validate all entities first
- validate all aliases
- validate all verse links
- validate all relationships
- only then replace metadata rows

## Error Handling

Operator-facing errors must be actionable and narrow.

Examples:

- `Theographic snapshot not found. Run 'bible-mcp fetch-theographic' first.`
- `Theographic sync requires imported verses because reference validation failed for Genesis 12:1.`
- `Overlay conflict: multiple external people map to canonical slug 'john'.`
- `Unsupported OSIS reference: Tob.1.1`

Avoid generic exceptions such as `sync failed` without context.

## Testing Strategy

### Fetch Tests

Add tests for:

- manifest generation
- per-file hashing
- re-fetch stability when target snapshot already exists
- failed fetch preserving previous valid snapshot

Use mocked HTTP responses. Do not hit GitHub in tests.

### Normalizer Tests

Add tests for:

- person normalization
- place normalization
- event normalization
- OSIS to runtime reference conversion
- relationship edge generation from Theographic fields
- per-entity verse-link caps

Use tiny synthetic raw JSON fixtures shaped like real Theographic records.

### Overlay Tests

Add tests for:

- stable canonical slug remaps for core people and places
- Korean alias append behavior
- display-name and description overrides
- collision detection when multiple external rows map to one canonical slug

### Import And Integration Tests

Add tests for:

- importing normalized Theographic bundles through the existing importer
- `fetch-theographic` CLI success and failure paths
- `sync-theographic` CLI success and failure paths
- `index` refusing to fetch remotely
- real-service lookup still working for people, places, event passages, and direct relations after sync

## Operational Workflow

The intended operator flow becomes:

1. `bible-mcp fetch-theographic`
2. `bible-mcp sync-theographic`
3. `bible-mcp index`
4. `bible-mcp serve`

If the operator updates the pinned Theographic ref, they repeat steps 1 and 2 before indexing again.

## Documentation Changes

Update `README.md` to explain:

- Theographic is the default large metadata source
- metadata fetch and sync are explicit commands
- indexing stays offline
- local metadata now combines a large English-first base with curated Korean overlay support for people and places
- source provenance and license obligations

## Open Risks

### Reference System Mismatch

Theographic verse identifiers use OSIS notation while the current runtime expects canonical English book names. The sync step must own this translation cleanly.

### Long-Tail English-First UX

Large imported coverage will still be English-first for most entities. This is acceptable for the first milestone but should be documented clearly.

### Core Entity Ambiguity

Some names such as `John` have multiple plausible canonical targets. The overlay must only pin the entities already intentionally supported by the local UX. It must not silently collapse distinct figures into one slug.

## Success Criteria

This design is complete when all of the following are true:

- a pinned Theographic snapshot can be fetched into a local reproducible cache
- sync can normalize thousands of people and places plus hundreds of events into the current metadata schema
- core curated `people + places` Korean aliases and stable slugs remain intact
- direct relation lookup still works over imported person relationships
- entity-linked passage lookup still works using canonical runtime references
- `index` remains local and deterministic
- test coverage exists for fetch, normalize, overlay, CLI, and import behavior

