# Bible MCP LLM Entity Rewrite Design

## Summary

Treat Bible MCP as a tool that always sits behind an LLM. When a user asks for a biblical entity in Korean but metadata is stored primarily in English, the LLM should retry the query with English candidates before giving up. The MCP server remains simple. Query interpretation and sequential retry live in the LLM layer.

The core example is `요단강`, where the user intent is correct but the underlying metadata may only expose `Jordan` or `Jordan River`.

## Goals

- improve entity lookup success for Korean user queries without a metadata rebuild
- keep MCP tool contracts stable
- prefer deterministic, low-cost retry behavior over broad semantic guessing
- stop on first successful entity resolution

## Non-Goals

- redesigning the metadata schema around multilingual aliases
- supporting direct non-LLM callers with the same fallback quality
- adding server-side translation logic to Bible MCP
- exposing retry internals to the end user

## Assumptions

- Bible MCP is always invoked by an LLM-capable client
- the client can make multiple MCP tool calls in sequence
- English metadata coverage is materially better than Korean metadata coverage
- the client prompt can encode retry rules reliably

## Why This Exists

Current entity lookup is limited by metadata language coverage. Even when the user names the correct biblical entity, a Korean query may miss because the stored canonical name or aliases are English-first. Expanding metadata coverage inside the server is expensive and brittle. Since the LLM is always present, the cheaper and more flexible solution is to let the LLM translate and retry entity queries.

## Chosen Approach

Use `LLM-only sequential rewrite`:

1. try the original user query first
2. if it returns no entity result, generate up to 5 English candidate queries
3. retry candidates one at a time in ranked order
4. stop at the first successful match
5. show the user only the final resolved result

This approach is preferred over server-side fallback because it matches the actual deployment model and avoids polluting the MCP server with translation policy.

## Tool Flow

### Primary Tool

The default tool is `route_entity_query`.

The LLM should call:

- `route_entity_query(query=<original user text>, limit=3)`

If that returns no useful result, the LLM should generate English candidates and retry:

- `route_entity_query(query=<candidate 1>, limit=3)`
- `route_entity_query(query=<candidate 2>, limit=3)`
- and so on, up to 5 candidates total

### Success Criteria

A tool call counts as successful when:

- `error` is `null`
- and at least one of these collections is non-empty:
  - `result.results`
  - `result.relations`
  - `result.passages`

The first successful call ends the retry chain.

## Candidate Generation Rules

The LLM may generate English candidates freely, but candidates must still be plausible names for the same biblical entity or event.

Allowed examples:

- `요단강` -> `Jordan`, `Jordan River`
- `출애굽` -> `Exodus`
- `부활` -> `Resurrection`

Disallowed behavior:

- unrelated semantic expansion
- speculative paraphrases not grounded in likely Bible naming
- retry chains longer than 5 candidates

Candidates should be:

- short
- ranked by likelihood
- explanation-free
- biased toward canonical Bible English names and common English aliases

## Ambiguity Handling

If a retry result resolves cleanly to one entity, use it.

If a retry result contains multiple distinct plausible entities:

- do not silently choose one
- ask the user a short follow-up question when needed
- or provide a narrowed answer only when the passage context clearly disambiguates the result

If all retries fail:

- report that no matching entity was found
- do not expose the internal retry list unless debugging is explicitly requested

## Prompt Contract

The front LLM needs an explicit instruction block equivalent to:

> When a Bible entity query returns no result, generate up to 5 English candidate queries that may refer to the same biblical entity in metadata. Prefer canonical Bible English names and common English aliases. Rank by likelihood. Retry sequentially and stop on the first successful result.

This instruction belongs in the MCP-using client prompt, not in the Bible MCP server.

## Error Handling

- hard MCP errors should stop the retry chain and surface the actual tool error
- empty results should continue the retry chain
- ambiguous multi-entity success should pause before answering definitively

## Testing Strategy

Validation should focus on the client-side orchestration layer that invokes Bible MCP:

- original Korean query succeeds without retry
- original Korean query fails and English retry succeeds
- retries stop on first success
- retries do not exceed 5 candidates
- ambiguous success does not silently choose the wrong entity
- complete failure returns a clean not-found answer

Representative cases:

- `요단강` -> `Jordan` or `Jordan River`
- `예루살렘` -> `Jerusalem`
- `부활` -> `Resurrection`
- `출애굽` -> `Exodus`

## Trade-Offs

### Benefits

- fixes the real user-facing problem where it occurs
- avoids a large metadata migration
- keeps Bible MCP implementation narrow and deterministic
- can evolve quickly by prompt changes alone

### Costs

- quality depends on the front LLM following the retry contract
- direct MCP callers do not benefit
- client orchestration becomes slightly more complex

## Implementation Boundary

This design does not change the Bible MCP server API. It adds orchestration behavior in the LLM client layer that calls Bible MCP tools.
