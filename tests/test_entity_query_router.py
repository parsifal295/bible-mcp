from __future__ import annotations

import pytest

from bible_mcp.services.entity_query_router import EntityQueryRouter


class FakeEntityService:
    def __init__(self) -> None:
        self.calls = []
        self.responses = {}

    def search(
        self,
        query: str,
        entity_type: str | None = None,
        limit: int = 5,
    ):
        self.calls.append(
            {
                "query": query,
                "entity_type": entity_type,
                "limit": limit,
            }
        )
        return self.responses.get((query, entity_type), [])


class FakeRelationService:
    def __init__(self, response) -> None:
        self.response = response
        self.calls = []

    def lookup(
        self,
        query: str,
        relation_type: str | None = None,
        entity_type: str | None = None,
        direction: str = "outgoing",
        limit: int = 5,
    ):
        self.calls.append(
            {
                "query": query,
                "relation_type": relation_type,
                "entity_type": entity_type,
                "direction": direction,
                "limit": limit,
            }
        )
        return self.response


class FakeEntityPassageService:
    def __init__(self, response) -> None:
        self.response = response
        self.calls = []

    def lookup(
        self,
        query: str,
        entity_type: str | None = None,
        limit: int = 5,
    ):
        self.calls.append(
            {
                "query": query,
                "entity_type": entity_type,
                "limit": limit,
            }
        )
        return self.response


def test_route_routes_jesus_disciples_to_relations_incoming() -> None:
    entity_service = FakeEntityService()
    relation_service = FakeRelationService(
        {
            "resolved_entity": {"display_name": "예수", "slug": "jesus"},
            "matches": [],
            "relations": [
                {"relation_type": "disciple_of", "display_name": "베드로", "slug": "peter"}
            ],
        }
    )
    router = EntityQueryRouter(
        entity_service,
        relation_service=relation_service,
        entity_passage_service=None,
    )

    result = router.route(" 예수의 제자들 ", limit=3)

    assert result["intent"] == "relations"
    assert result["parsed"] == {
        "original_query": " 예수의 제자들 ",
        "normalized_query": "예수의 제자들",
        "entity_text": "예수",
        "entity_type": "people",
        "relation_type": "disciple_of",
        "direction": "incoming",
        "target_tool": "get_entity_relations",
    }
    assert result["result"]["relations"][0]["slug"] == "peter"
    assert result["error"] is None
    assert relation_service.calls == [
        {
            "query": "예수",
            "relation_type": "disciple_of",
            "entity_type": "people",
            "direction": "incoming",
            "limit": 3,
        }
    ]


def test_route_routes_jerusalem_passage_query_to_entity_passages() -> None:
    entity_service = FakeEntityService()
    entity_service.responses[("예루살렘", "places")] = [
        {
            "entity_type": "places",
            "slug": "jerusalem",
            "display_name": "예루살렘",
            "description": None,
            "matched_by": "display_name",
        }
    ]
    entity_passage_service = FakeEntityPassageService(
        {
            "resolved_entity": {
                "entity_type": "places",
                "slug": "jerusalem",
                "display_name": "예루살렘",
                "description": None,
                "matched_by": "display_name",
            },
            "matches": [],
            "passages": [
                {
                    "reference": "Psalms 122:2",
                    "passage_text": "예루살렘아 우리 발이 네 성문 안에 섰도다",
                }
            ],
        }
    )
    router = EntityQueryRouter(
        entity_service,
        relation_service=None,
        entity_passage_service=entity_passage_service,
    )

    result = router.route("예루살렘 대표 구절", limit=1)

    assert result["intent"] == "passages"
    assert result["parsed"] == {
        "original_query": "예루살렘 대표 구절",
        "normalized_query": "예루살렘 대표 구절",
        "entity_text": "예루살렘",
        "entity_type": "places",
        "relation_type": None,
        "direction": None,
        "target_tool": "get_entity_passages",
    }
    assert result["result"]["passages"][0]["reference"] == "Psalms 122:2"
    assert result["error"] is None
    assert entity_passage_service.calls == [
        {
            "query": "예루살렘",
            "entity_type": "places",
            "limit": 1,
        }
    ]


def test_route_routes_event_queries_to_entity_search_results() -> None:
    entity_service = FakeEntityService()
    entity_service.responses[("출애굽 사건", "events")] = []
    entity_service.responses[("출애굽", "events")] = [
        {
            "entity_type": "events",
            "slug": "exodus",
            "display_name": "출애굽",
            "description": "이스라엘의 애굽 탈출 사건",
            "matched_by": "display_name",
        }
    ]
    router = EntityQueryRouter(
        entity_service,
        relation_service=None,
        entity_passage_service=None,
    )

    result = router.route("출애굽 사건", limit=2)

    assert result["intent"] == "entity_search"
    assert result["parsed"] == {
        "original_query": "출애굽 사건",
        "normalized_query": "출애굽 사건",
        "entity_text": "출애굽",
        "entity_type": "events",
        "relation_type": None,
        "direction": None,
        "target_tool": "search_entities",
    }
    assert result["result"] == {
        "results": [
            {
                "entity_type": "events",
                "slug": "exodus",
                "display_name": "출애굽",
                "description": "이스라엘의 애굽 탈출 사건",
                "matched_by": "display_name",
            }
        ]
    }
    assert result["error"] is None


def test_route_keeps_event_aliases_that_already_include_sageon() -> None:
    entity_service = FakeEntityService()
    entity_service.responses[("십자가 사건", "events")] = [
        {
            "entity_type": "events",
            "slug": "crucifixion",
            "display_name": "십자가 처형",
            "description": "예수의 십자가 죽음 사건",
            "matched_by": "alias",
        }
    ]
    router = EntityQueryRouter(
        entity_service,
        relation_service=None,
        entity_passage_service=None,
    )

    result = router.route("십자가 사건", limit=1)

    assert result["parsed"]["entity_text"] == "십자가 사건"
    assert result["result"] == {
        "results": [
            {
                "entity_type": "events",
                "slug": "crucifixion",
                "display_name": "십자가 처형",
                "description": "예수의 십자가 죽음 사건",
                "matched_by": "alias",
            }
        ]
    }
    assert entity_service.calls == [
        {"query": "십자가 사건", "entity_type": "events", "limit": 1},
    ]


def test_route_resolves_event_passage_queries_with_sageon_suffix() -> None:
    entity_service = FakeEntityService()
    entity_service.responses[("출애굽 사건", "events")] = []
    entity_service.responses[("출애굽", "events")] = [
        {
            "entity_type": "events",
            "slug": "exodus",
            "display_name": "출애굽",
            "description": "이스라엘의 애굽 탈출 사건",
            "matched_by": "display_name",
        }
    ]
    entity_passage_service = FakeEntityPassageService(
        {
            "resolved_entity": {
                "entity_type": "events",
                "slug": "exodus",
                "display_name": "출애굽",
                "description": "이스라엘의 애굽 탈출 사건",
                "matched_by": "display_name",
            },
            "matches": [],
            "passages": [
                {
                    "reference": "Exodus 12:41",
                    "passage_text": "애굽에서 나옴이라",
                }
            ],
        }
    )
    router = EntityQueryRouter(
        entity_service,
        relation_service=None,
        entity_passage_service=entity_passage_service,
    )

    result = router.route("출애굽 사건 대표 구절", limit=1)

    assert result["parsed"]["entity_text"] == "출애굽"
    assert result["parsed"]["entity_type"] == "events"
    assert result["result"]["passages"][0]["reference"] == "Exodus 12:41"
    assert entity_passage_service.calls == [
        {"query": "출애굽", "entity_type": "events", "limit": 1},
    ]


def test_route_routes_implicit_relation_forms() -> None:
    relation_service = FakeRelationService(
        {"resolved_entity": None, "matches": [], "relations": []}
    )
    router = EntityQueryRouter(
        FakeEntityService(),
        relation_service=relation_service,
        entity_passage_service=None,
    )

    father_result = router.route("다윗은 누구 아들인가")
    child_result = router.route("야곱의 자녀")

    assert father_result["parsed"]["entity_text"] == "다윗"
    assert father_result["parsed"]["relation_type"] == "father"
    assert father_result["parsed"]["direction"] == "incoming"
    assert child_result["parsed"]["entity_text"] == "야곱"
    assert child_result["parsed"]["relation_type"] == "child"
    assert child_result["parsed"]["direction"] == "outgoing"
    assert relation_service.calls == [
        {
            "query": "다윗",
            "relation_type": "father",
            "entity_type": "people",
            "direction": "incoming",
            "limit": 5,
        },
        {
            "query": "야곱",
            "relation_type": "father",
            "entity_type": "people",
            "direction": "outgoing",
            "limit": 5,
        },
    ]


def test_route_returns_intent_unavailable_for_missing_relation_service() -> None:
    router = EntityQueryRouter(
        FakeEntityService(),
        relation_service=None,
        entity_passage_service=None,
    )

    result = router.route("예수의 제자들")

    assert result == {
        "intent": "relations",
        "parsed": {
            "original_query": "예수의 제자들",
            "normalized_query": "예수의 제자들",
            "entity_text": "예수",
            "entity_type": "people",
            "relation_type": "disciple_of",
            "direction": "incoming",
            "target_tool": "get_entity_relations",
        },
        "result": None,
        "error": {
            "code": "intent_unavailable",
            "message": "relations intent is unavailable in this runtime",
        },
    }


def test_route_returns_intent_unavailable_for_missing_passage_service() -> None:
    entity_service = FakeEntityService()
    entity_service.responses[("예루살렘", "places")] = [
        {
            "entity_type": "places",
            "slug": "jerusalem",
            "display_name": "예루살렘",
            "description": None,
            "matched_by": "display_name",
        }
    ]
    router = EntityQueryRouter(
        entity_service,
        relation_service=None,
        entity_passage_service=None,
    )

    result = router.route("예루살렘 대표 구절")

    assert result["intent"] == "passages"
    assert result["result"] is None
    assert result["error"] == {
        "code": "intent_unavailable",
        "message": "passages intent is unavailable in this runtime",
    }


def test_route_does_not_force_place_type_for_non_place_names() -> None:
    entity_service = FakeEntityService()
    entity_service.responses[("산발랏", "people")] = [
        {
            "entity_type": "people",
            "slug": "sanballat",
            "display_name": "산발랏",
            "description": "대적자",
            "matched_by": "display_name",
        }
    ]
    entity_passage_service = FakeEntityPassageService(
        {
            "resolved_entity": {
                "entity_type": "people",
                "slug": "sanballat",
                "display_name": "산발랏",
                "description": "대적자",
                "matched_by": "display_name",
            },
            "matches": [],
            "passages": [],
        }
    )
    router = EntityQueryRouter(
        entity_service,
        relation_service=None,
        entity_passage_service=entity_passage_service,
    )

    result = router.route("산발랏 대표 구절")

    assert result["parsed"]["entity_type"] == "people"
    assert entity_passage_service.calls == [
        {
            "query": "산발랏",
            "entity_type": "people",
            "limit": 5,
        }
    ]


def test_route_does_not_force_place_type_for_names_containing_seong() -> None:
    entity_service = FakeEntityService()
    entity_service.responses[("성문지기", "people")] = [
        {
            "entity_type": "people",
            "slug": "gatekeeper",
            "display_name": "성문지기",
            "description": "직분",
            "matched_by": "display_name",
        }
    ]
    entity_passage_service = FakeEntityPassageService(
        {
            "resolved_entity": {
                "entity_type": "people",
                "slug": "gatekeeper",
                "display_name": "성문지기",
                "description": "직분",
                "matched_by": "display_name",
            },
            "matches": [],
            "passages": [],
        }
    )
    router = EntityQueryRouter(
        entity_service,
        relation_service=None,
        entity_passage_service=entity_passage_service,
    )

    result = router.route("성문지기 대표 구절")

    assert result["parsed"]["entity_type"] == "people"
    assert entity_passage_service.calls == [
        {
            "query": "성문지기",
            "entity_type": "people",
            "limit": 5,
        }
    ]


def test_route_reuses_probed_entity_search_results() -> None:
    entity_service = FakeEntityService()
    entity_service.responses[("아브라함", "people")] = [
        {
            "entity_type": "people",
            "slug": "abraham",
            "display_name": "아브라함",
            "description": "족장",
            "matched_by": "display_name",
        }
    ]
    router = EntityQueryRouter(
        entity_service,
        relation_service=None,
        entity_passage_service=None,
    )

    result = router.route("아브라함", limit=2)

    assert result["result"] == {
        "results": [
            {
                "entity_type": "people",
                "slug": "abraham",
                "display_name": "아브라함",
                "description": "족장",
                "matched_by": "display_name",
            }
        ]
    }
    assert entity_service.calls == [
        {"query": "아브라함", "entity_type": "places", "limit": 2},
        {"query": "아브라함", "entity_type": "events", "limit": 2},
        {"query": "아브라함", "entity_type": "people", "limit": 2},
    ]


def test_route_strips_place_location_suffixes_before_searching() -> None:
    entity_service = FakeEntityService()
    entity_service.responses[("요단 강", "places")] = [
        {
            "entity_type": "places",
            "slug": "jordan-river",
            "display_name": "요단강",
            "description": None,
            "matched_by": "display_name",
        }
    ]
    router = EntityQueryRouter(
        entity_service,
        relation_service=None,
        entity_passage_service=None,
    )

    result = router.route("요단 강 위치", limit=1)

    assert result["parsed"] == {
        "original_query": "요단 강 위치",
        "normalized_query": "요단 강 위치",
        "entity_text": "요단 강",
        "entity_type": "places",
        "relation_type": None,
        "direction": None,
        "target_tool": "search_entities",
    }
    assert result["result"] == {
        "results": [
            {
                "entity_type": "places",
                "slug": "jordan-river",
                "display_name": "요단강",
                "description": None,
                "matched_by": "display_name",
            }
        ]
    }
    assert entity_service.calls == [
        {"query": "요단 강", "entity_type": "places", "limit": 1},
    ]


def test_route_passes_through_relation_results_unchanged() -> None:
    entity_service = FakeEntityService()
    relation_service = FakeRelationService(
        {
            "resolved_entity": None,
            "matches": [
                {"entity_type": "people", "slug": "saul-a", "display_name": "사울"},
                {"entity_type": "people", "slug": "saul-b", "display_name": "사울"},
            ],
            "relations": [],
        }
    )
    router = EntityQueryRouter(
        entity_service,
        relation_service=relation_service,
        entity_passage_service=None,
    )

    result = router.route("사울의 아버지")

    assert result["intent"] == "relations"
    assert result["result"] == {
        "resolved_entity": None,
        "matches": [
            {"entity_type": "people", "slug": "saul-a", "display_name": "사울"},
            {"entity_type": "people", "slug": "saul-b", "display_name": "사울"},
        ],
        "relations": [],
    }


def test_route_rejects_invalid_limit() -> None:
    router = EntityQueryRouter(
        FakeEntityService(),
        relation_service=None,
        entity_passage_service=None,
    )

    with pytest.raises(ValueError, match="limit must be at least 1"):
        router.route("예수의 제자들", limit=0)
