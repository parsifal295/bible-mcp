# Bible MCP V2 Entity Passages Design

## Summary

Extend the current V2 metadata runtime so MCP clients can ask for representative Bible passages linked to an entity and receive both the normalized reference and the resolved passage text.

This slice reuses the existing `entity_verse_links` table and `PassageService.lookup()` path. It does not introduce semantic passage selection, context expansion, or graph traversal.

## Product Goal

Add a direct bridge from structured entity lookup to readable Bible text.

The target outcomes are:

- `get_entity_passages("예수")` returns representative linked passages for the resolved person
- `get_entity_passages("Jerusalem", entity_type="places")` returns linked place passages with resolved text
- `get_entity_passages("Resurrection", entity_type="events")` returns linked event passages with resolved text
- ambiguous entity queries return candidates instead of guessed passages

## Scope

### In Scope

- a dedicated runtime service for entity-linked passage retrieval
- a new MCP tool named `get_entity_passages`
- bundled `entity_verse_links` expansion for representative `people`, `places`, and `events`
- importer validation that bundled linked references resolve through the existing passage lookup path
- tests covering service behavior, MCP behavior, and default fixture bundle coverage

### Out Of Scope

- semantic ranking of entity passages
- context expansion around linked references
- merging linked passages into larger reading units
- automatic selection of “best” verses beyond fixture order
- natural-language relation parsing

## Current State

The codebase already has schema, fixture loading, and importer support for `entity_verse_links`, but no runtime service or MCP tool consumes those rows. Existing runtime metadata flows stop at entity resolution and direct relation lookup.

As a result, the application can resolve entities but cannot yet return the representative Bible passages already linked to them in the bundled metadata.

## Design Principles

- Reuse existing passage resolution logic instead of duplicating reference parsing.
- Keep ambiguity handling aligned with `RelationLookupService`.
- Preserve the current default entity lookup boundary: no `entity_type` still means `people`.
- Treat fixture order as the linked passage priority for this slice.
- Fail early during indexing when a bundled linked reference cannot be resolved at runtime.

## Chosen Approach

Use a dedicated `EntityPassageService` that:

1. resolves the entity through `EntityService`
2. reads linked references from `entity_verse_links`
3. resolves each linked reference through `PassageService.lookup()`

This keeps `entity_verse_links` as the source of truth for representative links while leaving all reference parsing and verse text assembly inside the already-tested passage service.

## Runtime Behavior

### Service Contract

Add `EntityPassageService`.

Inputs:

- `query` required
- `entity_type` optional
- `limit` optional

Outputs:

- `resolved_entity`
- `matches`
- `passages`

### Resolution Rules

- when `entity_type is None`, entity resolution stays scoped to `people`
- when `entity_type` is explicitly `people`, `places`, or `events`, resolution searches only that type
- unsupported `entity_type` values return:
  - `resolved_entity: None`
  - `matches: []`
  - `passages: []`

### Ambiguity Rules

- no entity matches -> empty result shape
- multiple entity matches -> return `matches`, leave `resolved_entity` as `None`, leave `passages` empty
- exactly one entity match -> return `resolved_entity` plus linked passages

### Passage Rules

Each returned passage contains:

- `reference`
- `passage_text`

The service reads links in `entity_verse_links` insertion order and limits after ordering. This means fixture/import order defines representative passage priority for this slice.

## MCP Tool Surface

Add a new MCP tool:

### `get_entity_passages`

Purpose:

- return representative linked Bible passages for one resolved entity

Inputs:

- `query` required
- `entity_type` optional
- `limit` optional

Outputs:

- `resolved_entity`
- `matches`
- `passages`
  - `reference`
  - `passage_text`

This tool keeps the existing entity and relation tools unchanged.

## Metadata Strategy

The default bundled fixture set expands `entity_verse_links` so all shipped active entity types have representative links.

Required shipped examples:

- people
  - keep the existing people links
- places
  - `jerusalem` -> `Psalm 122:2`
  - `bethlehem` -> `Micah 5:2`
  - `nazareth` -> `Matthew 2:23`
  - `galilee` -> `Matthew 4:15`
  - `jordan-river` -> `Matthew 3:13`
- events
  - `exodus` -> `Exodus 12:41`
  - `crucifixion` -> `Matthew 27:35`
  - `resurrection` -> `Matthew 28:6`

## Import Validation

The metadata importer expands validation for `entity_verse_links`.

In addition to checking entity existence, it verifies that each linked `reference` can be resolved through the same runtime lookup path used by `PassageService.lookup()`.

This keeps invalid bundled references from reaching runtime and turning into partial tool failures later.

## Testing Strategy

### Fixture And Import Tests

Add coverage for:

- default bundled `entity_verse_links` now containing `people`, `places`, and `events`
- importer rejecting an unresolved linked reference in a fixture bundle

### Service Tests

Add coverage for:

- no entity match -> empty result
- ambiguous entity match -> candidates only
- unique `people` entity -> representative linked passages with resolved text
- unique `places` entity -> representative linked passages with resolved text
- unique `events` entity -> representative linked passages with resolved text
- unsupported `entity_type` -> empty result

### MCP Tests

Add coverage for:

- `get_entity_passages` trims and forwards inputs correctly
- real-service MCP lookup returns linked passages for a place and an event from the default fixture bundle
- blank query and invalid limit behavior match the existing tool style

## Success Criteria

This slice is complete when all of the following are true:

- bundled `entity_verse_links` contain representative links for shipped `people`, `places`, and `events`
- indexing rejects unresolved linked references before runtime
- `get_entity_passages` returns `reference` and `passage_text` for uniquely resolved entities
- ambiguity handling mirrors the current relation lookup pattern
- the full automated test suite passes without breaking existing search, passage, or relation behavior
