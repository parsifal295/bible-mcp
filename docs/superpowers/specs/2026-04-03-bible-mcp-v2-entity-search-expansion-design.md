# Bible MCP V2 Entity Search Expansion Design

## Summary

Extend the current V2 metadata slice so `search_entities` can resolve `places` and `events` in addition to `people`.

This slice does not add new MCP tools and does not expand relation lookup. It only opens additional entity types behind explicit `entity_type` filtering while keeping default search behavior unchanged.

## Product Goal

Make the existing entity search tool useful for more than people without changing its default behavior for current clients.

The target user-visible outcomes are:

- `search_entities("예수")` still searches `people` only
- `search_entities("예루살렘", entity_type="places")` resolves place records
- `search_entities("resurrection", entity_type="events")` resolves event records
- Korean and English aliases work for the newly opened types

## Scope

### In Scope

- extend bundled metadata fixtures with minimal real `places` and `events` data
- expand `EntityService` to search `people`, `places`, and `events`
- keep the search response shape stable across all supported entity types
- expose `places` and `events` only when `entity_type` is explicitly provided
- add regression coverage for fixture import, service behavior, and MCP handler forwarding

### Out Of Scope

- mixed-type default search across people, places, and events
- changes to `get_entity_relations`
- `entity_verse_links` powered responses
- new relation types or relation traversal for places and events
- fuzzy, semantic, or substring entity matching

## Current State

The codebase already has schema and importer support for `places`, `events`, and `entity_verse_links`, but the shipped fixture bundle currently keeps `places.json` and `events.json` empty. The runtime `EntityService` is hard-coded to search `people` only and returns an empty list for any other `entity_type`.

As a result, the runtime surface implies broader metadata support than the bundled application data and search behavior actually provide.

## Design Principles

- Preserve the default V2 behavior for existing callers.
- Expand only one user-facing capability in this slice: typed entity lookup.
- Keep result ordering deterministic and inspectable.
- Reuse the current exact-match search model instead of introducing fuzzy behavior.
- Build the service change so additional typed search expansions reuse the same logic.

## Chosen Approach

Use a type registry inside `EntityService` instead of adding one-off `if entity_type == ...` branches per table.

The registry defines, per supported entity type:

- source table
- `slug` column
- `display_name` column
- `description` column or `NULL` literal
- whether alias lookup is supported

The search algorithm stays shared:

1. exact display-name match
2. exact alias match
3. exact slug match
4. deduplicate by `(entity_type, slug)`
5. sort by match priority, then display name, then slug

This keeps the current deterministic ranking while avoiding repeated query logic as more entity types become active.

## Runtime Behavior

### Default Search

`search_entities(query)` continues to search `people` only.

This is an explicit compatibility rule, not an implementation accident. The service must not silently widen default results to include places or events.

### Typed Search

`search_entities(query, entity_type="people")`, `entity_type="places"`, and `entity_type="events"` each search only the requested entity type.

The service does not perform cross-type search when an `entity_type` filter is present.

### Result Shape

The response shape remains:

- `entity_type`
- `slug`
- `display_name`
- `description`
- `matched_by`

`matched_by` values remain:

- `display_name`
- `alias`
- `slug`

`places` currently have no description column in SQLite, so place results return `description: null`.

## Metadata Fixture Strategy

The bundled repository fixtures become the source of truth for this slice.

The fixture bundle adds a minimal but real set of place and event records so the search expansion is observable and testable without relying on external datasets.

Recommended initial bundle:

- places: Jerusalem, Bethlehem, Nazareth, Galilee, Jordan River
- events: Exodus, Crucifixion, Resurrection

Each new entity type includes a minimal alias set with both Korean and representative English spellings where appropriate.

`entity_verse_links` is not part of the runtime response contract for this slice. Fixture rows may remain unchanged or expand for future work, but `search_entities` does not read or return verse-linked data here.

## Validation And Error Handling

Existing validation rules stay in place:

- blank `query` is rejected
- `limit < 1` is rejected

Unsupported `entity_type` values continue to produce an empty result set at the service layer.

The MCP handler does not introduce a new explicit entity-type validator in this slice. It forwards the optional `entity_type` as-is and preserves the current error contract for clients.

## Testing Strategy

### Service Tests

Add coverage for:

- default search still returning only `people`
- typed `places` search over display name, alias, and slug
- typed `events` search over display name, alias, and slug
- deterministic match ranking and deduplication for the new entity types

### Fixture And Import Tests

Add coverage for:

- default bundled fixtures importing non-empty `places` and `events`
- representative English aliases resolving correctly for each newly opened type

### MCP Tests

Keep the existing `search_entities` contract and add coverage that:

- `entity_type="places"` is forwarded unchanged
- `entity_type="events"` is forwarded unchanged
- blank query and invalid limit behavior remain unchanged

### Regression Boundary

Existing `get_entity_relations` behavior remains people-only and must continue to pass unchanged.

## Success Criteria

This slice is complete when all of the following are true:

- bundled metadata fixtures contain minimal real `places` and `events` records
- indexing imports those records into SQLite without changing the existing pipeline shape
- default `search_entities` behavior remains people-only
- typed `search_entities` calls can resolve places and events through display names, aliases, and slugs
- the full automated test suite passes without breaking relation lookup behavior
