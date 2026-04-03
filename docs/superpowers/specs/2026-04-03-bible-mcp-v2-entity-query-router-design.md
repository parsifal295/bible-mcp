# Bible MCP V2 Entity Query Router Design

## Goal

Add a small natural-language routing layer for entity-centric questions so users can ask one query such as `예수의 제자들` or `예루살렘 대표 구절` and receive a structured result without manually choosing between `search_entities`, `get_entity_relations`, and `get_entity_passages`.

This slice does not generate prose answers. It only interprets the query, selects one existing entity-oriented service, executes it, and returns both the parsed routing decision and the delegated result.

## Scope

This slice adds:

- a deterministic `EntityQueryRouter` service
- a new MCP tool `route_entity_query`
- natural-language intent detection for entity-centric questions
- structured output containing both parse metadata and delegated execution results

This slice does not add:

- free-form Korean answer generation
- general Bible search routing
- LLM-based intent classification
- new relation types
- chronology, map, or graph traversal features

## Product Shape

The router accepts a single user query and returns:

- the detected `intent`
- a normalized parse summary
- the delegated service result
- a structured `error` object only when the detected intent is unavailable at runtime

The new MCP tool is named `route_entity_query`.

## Architecture

### Router Service

Create a dedicated `EntityQueryRouter` service rather than embedding query parsing inside MCP handlers.

Responsibilities:

- normalize the incoming query
- classify intent as one of `entity_search`, `relations`, or `passages`
- extract the entity text from the natural-language query
- infer optional routing hints such as `entity_type`, `relation_type`, and `direction`
- delegate to exactly one existing service

Dependencies:

- `entity_service` required
- `relation_service` optional
- `entity_passage_service` optional

### MCP Layer

The MCP layer remains thin:

- validate `query` and `limit`
- call `EntityQueryRouter.route(query, limit=limit)`
- return the router payload as-is

The new MCP tool is registered only when `entity_service` is available, because `entity_search` is the base fallback behavior.

## Intent Model

### Supported Intents

- `relations`
- `passages`
- `entity_search`

### Priority

The router resolves intents in this order:

1. `relations`
2. `passages`
3. `entity_search`

This priority ensures that queries like `예수의 제자들` do not degrade into plain entity lookup.

## Query Interpretation Rules

### Relation Intent

The router should recognize both explicit and implicit relation expressions.

Supported relation phrases in this slice:

- `아버지`
- `어머니`
- `자녀`
- `아들`
- `딸`
- `형제`
- `자매`
- `배우자`
- `제자`
- `제자들`
- `누구 아들인가`

Relation mapping:

- `제자`, `제자들` -> `disciple_of`
- `아버지`, `누구 아들인가` -> `father`
- `어머니` -> `mother`
- `자녀` -> `child`
- `아들` -> `son`
- `딸` -> `daughter`
- `형제` -> `brother`
- `자매` -> `sister`
- `배우자` -> `spouse`

Direction rules for this slice:

- `예수의 제자들`, `다윗은 누구 아들인가`, `예수의 어머니` style queries map to `incoming`
- `야곱의 자녀`, `아브라함의 아들`, `베드로의 형제` style queries map to `outgoing`

If a relation phrase is detected, the router treats the query as `relations`. It does not silently fall back to `entity_search`.

### Passage Intent

Passage intent is triggered by these phrases:

- `대표 구절`
- `관련 구절`
- `연결 구절`
- `등장 구절`

Examples:

- `예루살렘 대표 구절`
- `부활 관련 구절`

### Entity Search Intent

If the query matches neither relation nor passage patterns, the router falls back to `entity_search`.

Examples:

- `예루살렘`
- `출애굽 사건`
- `다윗`

## Entity Extraction

The router strips recognized relation or passage phrases to compute `entity_text`.

Examples:

- `예수의 제자들` -> `예수`
- `다윗은 누구 아들인가` -> `다윗`
- `야곱의 자녀` -> `야곱`
- `예루살렘 대표 구절` -> `예루살렘`

This slice uses deterministic string and regex rules only. It does not use morphological analysis.

If entity extraction fails cleanly, the router falls back to `entity_search` with the normalized query.

## Entity Type Hints

The router may infer an optional `entity_type` hint.

Rules:

- `relations` defaults to `people`
- if the query contains `사건`, hint `events`
- if the query contains place-like suffixes or words such as `성`, `강`, `바다`, `산`, `광야`, `도시`, hint `places`
- otherwise leave `entity_type` as `None`

The hint narrows routing when the rule is reliable, but inference is intentionally shallow in this slice.

## Delegation Rules

### Relations

When `intent=relations`, call:

- `relation_service.lookup(query=entity_text, relation_type=..., entity_type=..., direction=..., limit=...)`

### Passages

When `intent=passages`, call:

- `entity_passage_service.lookup(query=entity_text, entity_type=..., limit=...)`

### Entity Search

When `intent=entity_search`, call:

- `entity_service.search(query=entity_text_or_normalized_query, entity_type=..., limit=...)`

The router never calls more than one downstream service per request.

## Response Contract

The router returns this shape:

```json
{
  "intent": "relations",
  "parsed": {
    "original_query": "예수의 제자들",
    "normalized_query": "예수의 제자들",
    "entity_text": "예수",
    "entity_type": "people",
    "relation_type": "disciple_of",
    "direction": "incoming",
    "target_tool": "get_entity_relations"
  },
  "result": {
    "resolved_entity": {},
    "matches": [],
    "relations": []
  },
  "error": null
}
```

Rules:

- `intent` is always one of `entity_search`, `relations`, `passages`
- `parsed` always exists
- `result` contains the delegated service result unchanged
- `error` is `null` on success

For `entity_search`, the delegated result shape is:

```json
{"results": [...]}
```

For `relations`, the delegated result shape is:

```json
{"resolved_entity": ..., "matches": [...], "relations": [...]}
```

For `passages`, the delegated result shape is:

```json
{"resolved_entity": ..., "matches": [...], "passages": [...]}
```

## Runtime Unavailability

Because `relation_service` and `entity_passage_service` are optional runtime collaborators, the router must not fake a fallback result when a detected intent cannot be served.

If the detected intent is unavailable:

- `result` is `null`
- `error` is populated

Error shape:

```json
{
  "code": "intent_unavailable",
  "message": "relations intent is unavailable in this runtime"
}
```

This applies to:

- `relations` when `relation_service` is absent
- `passages` when `entity_passage_service` is absent

`entity_search` is always available when the router itself is registered.

## Partial Schema Safety

The router relies on downstream services that must behave safely on partial schemas.

Expected behavior for this slice:

- `EntityService` must return `[]` rather than crash when explicitly asked for an entity type whose backing table is missing
- alias matching must be skipped safely if `entity_aliases` is missing
- `EntityPassageService` must return an empty `passages` list rather than crash when `entity_verse_links` is missing

This requirement keeps the routing layer consistent with the current runtime gating strategy and prevents partial-schema regressions from leaking as SQLite errors.

## CLI and MCP Registration

### CLI

`serve()` should instantiate `EntityQueryRouter` whenever `entity_service` is available.

It should pass through optional collaborators:

- `relation_service`
- `entity_passage_service`

### MCP

Register `route_entity_query(query: str, limit: int = 5)` only when the router service is available.

The new tool should:

- trim blank queries with the existing `_require_text`
- validate `limit` with `_require_limit`
- delegate to the router

## Examples

### Relation Query

Input:

```text
예수의 제자들
```

Expected parse:

- `intent=relations`
- `entity_text=예수`
- `entity_type=people`
- `relation_type=disciple_of`
- `direction=incoming`
- `target_tool=get_entity_relations`

### Passage Query

Input:

```text
예루살렘 대표 구절
```

Expected parse:

- `intent=passages`
- `entity_text=예루살렘`
- `entity_type=places`
- `target_tool=get_entity_passages`

### Entity Search Query

Input:

```text
출애굽 사건
```

Expected parse:

- `intent=entity_search`
- `entity_text=출애굽 사건`
- `entity_type=events`
- `target_tool=search_entities`

## Testing

### Router Unit Tests

Add deterministic tests for:

- `예수의 제자들` -> `relations`, `disciple_of`, `incoming`
- `다윗은 누구 아들인가` -> `relations`, `father`, `incoming`
- `야곱의 자녀` -> `relations`, `child`, `outgoing`
- `예루살렘 대표 구절` -> `passages`
- `출애굽 사건` -> `entity_search`, `events`

### Delegation Tests

Add tests that verify:

- ambiguous and no-match results pass through unchanged
- `intent_unavailable` is returned when relation or passage collaborators are absent
- `entity_search` continues to work without optional collaborators

### MCP Tests

Add handler and tool-level tests for:

- trim and limit validation
- real-service routing for one relation query and one passage query
- correct registration behavior for `route_entity_query`

### Regression Coverage

Maintain coverage for:

- existing `search_entities`
- existing `get_entity_relations`
- existing `get_entity_passages`
- partial-schema safety in downstream entity services

## Acceptance Criteria

This slice is complete when:

- a new `route_entity_query` MCP tool exists
- entity-centric natural-language queries route deterministically into exactly one existing service
- relation, passage, and search intents all return structured parse metadata plus delegated results
- unavailable intents return structured `intent_unavailable` errors instead of fake fallback answers
- the automated test suite passes without regressing existing entity search, relation lookup, or entity passage behavior
