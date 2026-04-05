# LLM Entity Rewrite Integration Contract

This guide documents the client-side retry contract for LLM clients that need to resolve Korean entity input against English-first Bible metadata.

## What This Solves

Bible metadata is indexed with English canonical names and English slugs. Users, however, often ask in Korean, for example `요단강`. A client that only sends the original Korean query may miss a valid entity because the metadata surface is English-first.

The integration contract is simple: let the client try the original query first, then rewrite and retry in English only when classification returns `not_found`.

## Required Flow

1. Call `route_entity_query` with the original query exactly as the user entered it.
2. If classification returns `not_found`, generate up to 5 English candidate queries.
3. Retry those candidates sequentially, one at a time.
4. Stop on the first successful result.
5. Hide retry internals unless debugging is explicitly requested.

## Classification Rules

Use the raw `route_entity_query` response to classify the outcome:

- `error != null` is a hard stop.
- Multiple distinct entity slugs across `resolved_entity`, `results`, and `matches` means `ambiguous`.
- A present `resolved_entity` counts as `success`.
- Otherwise, non-empty `results`, `relations`, or `passages` counts as `success`.
- Otherwise, return `not_found`.

The helper in [src/bible_mcp/client_patterns/entity_retry.py](../../src/bible_mcp/client_patterns/entity_retry.py) uses this same contract when it classifies route responses into `success`, `not_found`, `ambiguous`, or `error`.

## Prompt Contract

The retry prompt should match the helper output from `build_entity_retry_prompt(max_candidates=5)`:

```text
retry only when the original query returns no result.
generate up to 5 English candidate queries.
use canonical Bible English names and common English aliases.
rank by likelihood.
retry sequentially.
stop on the first successful result.
```

If you change the retry limit, update the numeric line so the prompt still matches the helper contract.

## Example

`요단강` should flow through the client as:

`요단강` -> `Jordan` -> `Jordan River`

In practice, the client sends the original query first, sees that it is not resolved, then retries the English candidates until one returns a successful entity result. If the first retry succeeds, later candidates are never sent.

## Debugging Guidance

The client should keep retry bookkeeping out of the user-facing experience. Only surface the retry chain, attempted candidates, or classification details when a debugging mode is requested.
