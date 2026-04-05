from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Sequence


ResponseStatus = Literal["success", "not_found", "ambiguous", "error"]


@dataclass(frozen=True)
class RetryResolution:
    status: ResponseStatus
    attempted_queries: list[str]
    matched_query: str | None
    response: dict[str, Any] | None


def _payload_items(payload: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _distinct_entity_slugs(response: dict[str, Any]) -> set[str]:
    result = response.get("result")
    slugs: set[str] = set()

    if not isinstance(result, dict):
        return slugs

    resolved = result.get("resolved_entity")
    if isinstance(resolved, dict):
        slug = resolved.get("slug")
        if isinstance(slug, str) and slug.strip():
            slugs.add(slug.strip())

    for key in ("results", "matches"):
        for item in _payload_items(result, key):
            slug = item.get("slug")
            if isinstance(slug, str) and slug.strip():
                slugs.add(slug.strip())

    return slugs


def classify_route_entity_query_response(response: dict[str, Any]) -> ResponseStatus:
    if response.get("error") is not None:
        return "error"

    result = response.get("result")
    if not isinstance(result, dict):
        return "not_found"

    resolved_entity = result.get("resolved_entity")
    has_payload = isinstance(resolved_entity, dict) or any(
        bool(_payload_items(result, key)) for key in ("results", "relations", "passages")
    )
    if not has_payload:
        return "not_found"

    if len(_distinct_entity_slugs(response)) > 1:
        return "ambiguous"

    return "success"


def build_entity_retry_prompt(max_candidates: int = 5) -> str:
    return (
        "When a Bible entity query returns no result, generate up to "
        f"{max_candidates} English candidate queries that may refer to the same "
        "biblical entity in metadata. Prefer canonical Bible English names and "
        "common English aliases. Rank by likelihood. Retry sequentially and stop "
        "on the first successful result."
    )


def normalize_retry_candidates(
    candidates: Sequence[str],
    *,
    max_candidates: int = 5,
) -> list[str]:
    normalized: list[str] = []
    for candidate in candidates:
        text = " ".join(str(candidate).split())
        if not text or text in normalized:
            continue
        normalized.append(text)
        if len(normalized) >= max_candidates:
            break
    return normalized


def resolve_entity_query_with_retries(
    *,
    original_query: str,
    english_candidates: Sequence[str],
    route_query: Callable[[str, int], dict[str, Any]],
    limit: int = 3,
    max_candidates: int = 5,
) -> RetryResolution:
    attempted_queries: list[str] = []
    retry_queries = [
        original_query,
        *normalize_retry_candidates(
            english_candidates,
            max_candidates=max_candidates,
        ),
    ]

    for query in retry_queries:
        attempted_queries.append(query)
        response = route_query(query, limit)
        status = classify_route_entity_query_response(response)

        if status == "success":
            return RetryResolution(
                status="success",
                attempted_queries=attempted_queries,
                matched_query=query,
                response=response,
            )

        if status in {"ambiguous", "error"}:
            return RetryResolution(
                status=status,
                attempted_queries=attempted_queries,
                matched_query=None,
                response=response,
            )

    return RetryResolution(
        status="not_found",
        attempted_queries=attempted_queries,
        matched_query=None,
        response=None,
    )
