from bible_mcp.client_patterns.entity_retry import (
    build_entity_retry_prompt,
    classify_route_entity_query_response,
    resolve_entity_query_with_retries,
)


def test_classify_response_returns_not_found_for_empty_entity_results() -> None:
    response = {
        "intent": "entity_search",
        "result": {"results": []},
        "error": None,
    }

    assert classify_route_entity_query_response(response) == "not_found"


def test_classify_response_returns_success_for_single_entity_result() -> None:
    response = {
        "intent": "entity_search",
        "result": {
            "results": [
                {
                    "entity_type": "places",
                    "slug": "jordan-river",
                    "display_name": "Jordan",
                }
            ]
        },
        "error": None,
    }

    assert classify_route_entity_query_response(response) == "success"


def test_classify_response_returns_success_for_resolved_entity_without_payload_lists() -> None:
    response = {
        "intent": "passages",
        "result": {
            "resolved_entity": {
                "entity_type": "places",
                "slug": "jerusalem",
                "display_name": "예루살렘",
            },
            "matches": [],
            "passages": [],
        },
        "error": None,
    }

    assert classify_route_entity_query_response(response) == "success"


def test_classify_response_returns_ambiguous_for_multiple_entity_slugs() -> None:
    response = {
        "intent": "entity_search",
        "result": {
            "results": [
                {
                    "entity_type": "places",
                    "slug": "jordan-river",
                    "display_name": "Jordan",
                },
                {
                    "entity_type": "places",
                    "slug": "plain-of-jordan",
                    "display_name": "Plain of Jordan",
                },
            ]
        },
        "error": None,
    }

    assert classify_route_entity_query_response(response) == "ambiguous"


def test_classify_response_returns_error_when_tool_error_exists() -> None:
    response = {
        "intent": "entity_search",
        "result": None,
        "error": {"code": "tool_failed", "message": "upstream timeout"},
    }

    assert classify_route_entity_query_response(response) == "error"


def test_build_entity_retry_prompt_mentions_sequential_retry_and_candidate_limit() -> None:
    prompt = build_entity_retry_prompt(max_candidates=5)

    assert "up to 5 English candidate queries" in prompt
    assert "Retry sequentially" in prompt
    assert "first successful result" in prompt


def test_resolve_entity_query_with_retries_stops_on_first_success() -> None:
    calls: list[tuple[str, int]] = []
    responses = {
        "요단강": {"intent": "entity_search", "result": {"results": []}, "error": None},
        "Jordan": {"intent": "entity_search", "result": {"results": []}, "error": None},
        "Jordan River": {
            "intent": "entity_search",
            "result": {
                "results": [
                    {
                        "entity_type": "places",
                        "slug": "jordan-river",
                        "display_name": "Jordan",
                    }
                ]
            },
            "error": None,
        },
    }

    def fake_route_query(query: str, limit: int) -> dict:
        calls.append((query, limit))
        return responses[query]

    resolution = resolve_entity_query_with_retries(
        original_query="요단강",
        english_candidates=["Jordan", "Jordan River", "River Jordan"],
        route_query=fake_route_query,
        limit=3,
        max_candidates=5,
    )

    assert resolution.status == "success"
    assert resolution.matched_query == "Jordan River"
    assert resolution.attempted_queries == ["요단강", "Jordan", "Jordan River"]
    assert calls == [("요단강", 3), ("Jordan", 3), ("Jordan River", 3)]


def test_resolve_entity_query_with_retries_truncates_and_deduplicates_candidates() -> None:
    calls: list[str] = []

    def fake_route_query(query: str, limit: int) -> dict:
        calls.append(query)
        return {"intent": "entity_search", "result": {"results": []}, "error": None}

    resolution = resolve_entity_query_with_retries(
        original_query="부활",
        english_candidates=[
            "Resurrection",
            "Resurrection",
            "The Resurrection",
            "Jesus Resurrection",
            "Rising Again",
            "Raised from the Dead",
            "Easter",
        ],
        route_query=fake_route_query,
        limit=2,
        max_candidates=5,
    )

    assert resolution.status == "not_found"
    assert resolution.attempted_queries == [
        "부활",
        "Resurrection",
        "The Resurrection",
        "Jesus Resurrection",
        "Rising Again",
        "Raised from the Dead",
    ]
    assert calls == resolution.attempted_queries


def test_resolve_entity_query_with_retries_returns_ambiguous_without_further_retry() -> None:
    calls: list[str] = []

    def fake_route_query(query: str, limit: int) -> dict:
        calls.append(query)
        if query == "출애굽":
            return {"intent": "entity_search", "result": {"results": []}, "error": None}
        return {
            "intent": "entity_search",
            "result": {
                "results": [
                    {"entity_type": "events", "slug": "exodus", "display_name": "Exodus"},
                    {
                        "entity_type": "books",
                        "slug": "book-of-exodus",
                        "display_name": "Exodus",
                    },
                ]
            },
            "error": None,
        }

    resolution = resolve_entity_query_with_retries(
        original_query="출애굽",
        english_candidates=["Exodus", "The Exodus"],
        route_query=fake_route_query,
        limit=3,
        max_candidates=5,
    )

    assert resolution.status == "ambiguous"
    assert resolution.matched_query is None
    assert resolution.attempted_queries == ["출애굽", "Exodus"]
    assert calls == ["출애굽", "Exodus"]


def test_resolve_entity_query_with_retries_stops_on_hard_error() -> None:
    calls: list[str] = []

    def fake_route_query(query: str, limit: int) -> dict:
        calls.append(query)
        return {
            "intent": "entity_search",
            "result": None,
            "error": {"code": "tool_failed", "message": "server unavailable"},
        }

    resolution = resolve_entity_query_with_retries(
        original_query="예루살렘",
        english_candidates=["Jerusalem"],
        route_query=fake_route_query,
        limit=3,
        max_candidates=5,
    )

    assert resolution.status == "error"
    assert resolution.attempted_queries == ["예루살렘"]
    assert calls == ["예루살렘"]
