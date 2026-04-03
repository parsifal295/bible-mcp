# Bible MCP V2 Entity Query Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic `route_entity_query` layer that interprets entity-centric natural-language questions and routes each query into exactly one existing entity service.

**Architecture:** Introduce a dedicated `EntityQueryRouter` service that parses relation, passage, and fallback entity-search intents using regex and deterministic probing. Keep MCP handlers thin by routing through the new service, and wire the router into `serve()` whenever `entity_service` is available so the MCP surface gains one high-level entity query tool without changing the underlying search, relation, or passage services.

**Tech Stack:** Python, SQLite, FastMCP, pytest

---

## File Structure

- Create: `src/bible_mcp/services/entity_query_router.py`
  Deterministic entity-query parser and delegator.
- Create: `tests/test_entity_query_router.py`
  Unit coverage for parsing, routing, unavailable intents, and result passthrough.
- Modify: `src/bible_mcp/mcp_server.py`
  Add optional `entity_query_router` wiring plus `route_entity_query` MCP handler and tool registration.
- Modify: `src/bible_mcp/cli.py`
  Instantiate `EntityQueryRouter` in `serve()` whenever `entity_service` is available, passing through optional collaborators.
- Modify: `tests/test_mcp_tools.py`
  Add handler regressions, real-service routing integration, and MCP registration assertions for `route_entity_query`.
- Modify: `tests/test_related_summary_entities.py`
  Update CLI wiring capture and exact tool-set assertions for the new router collaborator and MCP tool.

### Task 1: Add `EntityQueryRouter` service

**Files:**
- Create: `src/bible_mcp/services/entity_query_router.py`
- Create: `tests/test_entity_query_router.py`

- [ ] **Step 1: Write the failing router tests**

Create `tests/test_entity_query_router.py` with this content:

```python
from __future__ import annotations

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
    entity_service.responses[("출애굽 사건", "events")] = [
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
        "entity_text": "출애굽 사건",
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
```

- [ ] **Step 2: Run the new router tests to confirm the service does not exist yet**

Run:

```bash
./.venv/bin/python -m pytest tests/test_entity_query_router.py -v
```

Expected:

```text
ERROR collecting tests/test_entity_query_router.py
ModuleNotFoundError: No module named 'bible_mcp.services.entity_query_router'
```

- [ ] **Step 3: Write the minimal router implementation**

Create `src/bible_mcp/services/entity_query_router.py` with this content:

```python
from __future__ import annotations

import re


_RELATION_RULES = (
    (re.compile(r"^(?P<entity>.+?)은 누구 아들인가$"), "father", "incoming"),
    (re.compile(r"^(?P<entity>.+?)의 아버지$"), "father", "incoming"),
    (re.compile(r"^(?P<entity>.+?)의 어머니$"), "mother", "incoming"),
    (re.compile(r"^(?P<entity>.+?)의 자녀$"), "child", "outgoing"),
    (re.compile(r"^(?P<entity>.+?)의 아들$"), "son", "outgoing"),
    (re.compile(r"^(?P<entity>.+?)의 딸$"), "daughter", "outgoing"),
    (re.compile(r"^(?P<entity>.+?)의 형제$"), "brother", "outgoing"),
    (re.compile(r"^(?P<entity>.+?)의 자매$"), "sister", "outgoing"),
    (re.compile(r"^(?P<entity>.+?)의 배우자$"), "spouse", "outgoing"),
    (re.compile(r"^(?P<entity>.+?)의 제자들?$"), "disciple_of", "incoming"),
)
_PASSAGE_PATTERN = re.compile(
    r"^(?P<entity>.+?)\s*(대표 구절|관련 구절|연결 구절|등장 구절)$"
)
_PLACE_HINT_TOKENS = ("성", "강", "바다", "산", "광야", "도시")
_PROBE_ENTITY_TYPES = ("places", "events", "people")


class EntityQueryRouter:
    def __init__(
        self,
        entity_service,
        relation_service=None,
        entity_passage_service=None,
    ) -> None:
        self.entity_service = entity_service
        self.relation_service = relation_service
        self.entity_passage_service = entity_passage_service

    def route(self, query: str, limit: int = 5):
        limit = int(limit)
        if limit < 1:
            raise ValueError("limit must be at least 1")

        original_query = query
        normalized_query = str(query).strip()
        parsed = self._parse(normalized_query, original_query)

        if parsed["intent"] == "relations":
            if self.relation_service is None:
                return self._intent_unavailable(parsed, "relations")
            result = self.relation_service.lookup(
                parsed["entity_text"],
                relation_type=parsed["relation_type"],
                entity_type=parsed["entity_type"],
                direction=parsed["direction"],
                limit=limit,
            )
        elif parsed["intent"] == "passages":
            if self.entity_passage_service is None:
                return self._intent_unavailable(parsed, "passages")
            result = self.entity_passage_service.lookup(
                parsed["entity_text"],
                entity_type=parsed["entity_type"],
                limit=limit,
            )
        else:
            result = {
                "results": self.entity_service.search(
                    parsed["entity_text"],
                    entity_type=parsed["entity_type"],
                    limit=limit,
                )
            }

        return {
            "intent": parsed["intent"],
            "parsed": {
                "original_query": original_query,
                "normalized_query": normalized_query,
                "entity_text": parsed["entity_text"],
                "entity_type": parsed["entity_type"],
                "relation_type": parsed["relation_type"],
                "direction": parsed["direction"],
                "target_tool": parsed["target_tool"],
            },
            "result": result,
            "error": None,
        }

    def _parse(self, normalized_query: str, original_query: str):
        relation = self._parse_relation(normalized_query)
        if relation is not None:
            relation["original_query"] = original_query
            return relation

        passage = self._parse_passage(normalized_query)
        if passage is not None:
            passage["original_query"] = original_query
            return passage

        return {
            "intent": "entity_search",
            "original_query": original_query,
            "normalized_query": normalized_query,
            "entity_text": normalized_query,
            "entity_type": self._infer_entity_type(normalized_query, normalized_query, "entity_search"),
            "relation_type": None,
            "direction": None,
            "target_tool": "search_entities",
        }

    def _parse_relation(self, normalized_query: str):
        for pattern, relation_type, direction in _RELATION_RULES:
            match = pattern.match(normalized_query)
            if match is None:
                continue
            entity_text = match.group("entity").strip()
            return {
                "intent": "relations",
                "normalized_query": normalized_query,
                "entity_text": entity_text,
                "entity_type": "people",
                "relation_type": relation_type,
                "direction": direction,
                "target_tool": "get_entity_relations",
            }
        return None

    def _parse_passage(self, normalized_query: str):
        match = _PASSAGE_PATTERN.match(normalized_query)
        if match is None:
            return None

        entity_text = match.group("entity").strip()
        return {
            "intent": "passages",
            "normalized_query": normalized_query,
            "entity_text": entity_text,
            "entity_type": self._infer_entity_type(entity_text, normalized_query, "passages"),
            "relation_type": None,
            "direction": None,
            "target_tool": "get_entity_passages",
        }

    def _infer_entity_type(
        self,
        entity_text: str,
        normalized_query: str,
        intent: str,
    ) -> str | None:
        if intent == "relations":
            return "people"

        if "사건" in normalized_query:
            return "events"

        if any(token in normalized_query for token in _PLACE_HINT_TOKENS):
            return "places"

        for entity_type in _PROBE_ENTITY_TYPES:
            matches = self.entity_service.search(entity_text, entity_type=entity_type, limit=1)
            if matches:
                return entity_type
        return None

    def _intent_unavailable(self, parsed: dict, intent: str):
        return {
            "intent": parsed["intent"],
            "parsed": {
                "original_query": parsed["original_query"],
                "normalized_query": parsed["normalized_query"],
                "entity_text": parsed["entity_text"],
                "entity_type": parsed["entity_type"],
                "relation_type": parsed["relation_type"],
                "direction": parsed["direction"],
                "target_tool": parsed["target_tool"],
            },
            "result": None,
            "error": {
                "code": "intent_unavailable",
                "message": f"{intent} intent is unavailable in this runtime",
            },
        }
```

- [ ] **Step 4: Run the router tests to verify they pass**

Run:

```bash
./.venv/bin/python -m pytest tests/test_entity_query_router.py -q
```

Expected:

```text
6 passed
```

- [ ] **Step 5: Commit the router service**

Run:

```bash
git add src/bible_mcp/services/entity_query_router.py tests/test_entity_query_router.py
git commit -m "feat: add entity query router"
```

### Task 2: Wire `route_entity_query` through MCP and CLI

**Files:**
- Modify: `src/bible_mcp/mcp_server.py`
- Modify: `src/bible_mcp/cli.py`
- Modify: `tests/test_mcp_tools.py`
- Modify: `tests/test_related_summary_entities.py`

- [ ] **Step 1: Write the failing MCP and CLI wiring tests**

Add this fake router and the new tests to `tests/test_mcp_tools.py`:

```python
class FakeEntityQueryRouter:
    def __init__(self) -> None:
        self.calls = []

    def route(self, query: str, limit: int = 5):
        self.calls.append({"query": query, "limit": limit})
        return {
            "intent": "entity_search",
            "parsed": {
                "original_query": query,
                "normalized_query": query,
                "entity_text": query,
                "entity_type": None,
                "relation_type": None,
                "direction": None,
                "target_tool": "search_entities",
            },
            "result": {
                "results": [
                    {"entity_type": "people", "slug": "abraham", "display_name": "아브라함"}
                ]
            },
            "error": None,
        }


def test_route_entity_query_handler_trims_query_and_forwards_limit() -> None:
    entity_query_router = FakeEntityQueryRouter()
    handlers = build_tool_handlers(
        FakeSearchService(),
        FakePassageService(),
        None,
        Mock(),
        FakeEntityService(),
        None,
        FakeEntityPassageService(),
        entity_query_router,
    )

    result = handlers["route_entity_query"]({"query": " 예수의 제자들 ", "limit": 2})

    assert entity_query_router.calls == [{"query": "예수의 제자들", "limit": 2}]
    assert result["intent"] == "entity_search"
    assert result["result"]["results"][0]["slug"] == "abraham"


def test_route_entity_query_handler_rejects_invalid_limit() -> None:
    handlers = build_tool_handlers(
        FakeSearchService(),
        FakePassageService(),
        None,
        Mock(),
        FakeEntityService(),
        None,
        FakeEntityPassageService(),
        FakeEntityQueryRouter(),
    )

    with pytest.raises(ValueError, match="limit must be at least 1"):
        handlers["route_entity_query"]({"query": "예수의 제자들", "limit": 0})


def test_route_entity_query_handler_routes_relation_and_passage_queries_with_real_services(
    tmp_path: Path,
) -> None:
    from bible_mcp.services.entity_query_router import EntityQueryRouter
    from bible_mcp.services.relation_service import RelationLookupService

    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)
    _seed_default_bundle_verses(conn)
    import_metadata_fixtures(conn)

    entity_service = EntityService(conn)
    passage_service = PassageService(conn)
    relation_service = RelationLookupService(conn, entity_service)
    entity_passage_service = EntityPassageService(conn, entity_service, passage_service)
    entity_query_router = EntityQueryRouter(
        entity_service,
        relation_service=relation_service,
        entity_passage_service=entity_passage_service,
    )
    handlers = build_tool_handlers(
        FakeSearchService(),
        passage_service,
        None,
        None,
        entity_service,
        relation_service,
        entity_passage_service,
        entity_query_router,
    )

    relation_result = handlers["route_entity_query"]({"query": "예수의 제자들", "limit": 5})
    passage_result = handlers["route_entity_query"]({"query": "예루살렘 대표 구절", "limit": 1})

    assert relation_result["intent"] == "relations"
    assert relation_result["parsed"]["relation_type"] == "disciple_of"
    assert relation_result["parsed"]["direction"] == "incoming"
    assert {row["slug"] for row in relation_result["result"]["relations"]} == {
        "john",
        "peter",
    }

    assert passage_result["intent"] == "passages"
    assert passage_result["parsed"]["entity_type"] == "places"
    assert passage_result["result"]["passages"] == [
        {
            "reference": "Psalms 122:2",
            "passage_text": "Our feet shall stand within thy gates, O Jerusalem.",
        }
    ]


def test_create_mcp_server_registers_route_entity_query_when_router_is_present() -> None:
    mcp = create_mcp_server(
        FakeSearchService(),
        FakePassageService(),
        None,
        None,
        FakeEntityService(),
        None,
        None,
        FakeEntityQueryRouter(),
    )
    tools = asyncio.run(mcp.list_tools())

    assert {tool.name for tool in tools} == {
        "search_bible",
        "lookup_passage",
        "expand_context",
        "search_entities",
        "route_entity_query",
    }
```

Update `tests/test_related_summary_entities.py` like this:

```python
from bible_mcp.services.entity_query_router import EntityQueryRouter
```

Update both `fake_create_mcp_server(...)` helpers to accept and capture `entity_query_router`:

```python
def fake_create_mcp_server(
    search_service,
    passage_service,
    related_service,
    summarizer,
    entity_service,
    relation_service,
    entity_passage_service,
    entity_query_router,
):
    captured["related_service"] = related_service
    captured["summarizer"] = summarizer
    captured["entity_service"] = entity_service
    captured["relation_service"] = relation_service
    captured["entity_passage_service"] = entity_passage_service
    captured["entity_query_router"] = entity_query_router

    class FakeServer:
        def run(self):
            return None

    return FakeServer()
```

Add assertions:

```python
assert captured["entity_query_router"] is None
```

for the no-study-tools case, and:

```python
assert isinstance(captured["entity_query_router"], EntityQueryRouter)
```

for the full-schema study-tools case.

Also extend `test_serve_omits_entity_passage_service_when_entity_verse_links_are_missing(...)` so it keeps asserting:

```python
assert captured["entity_passage_service"] is None
assert isinstance(captured["entity_query_router"], EntityQueryRouter)
```

That locks in the contract that the router is available whenever `entity_service` exists, even if passage intent must later return `intent_unavailable`.

Update the exact tool-set assertions:

```python
assert {tool.name for tool in tools} == {
    "search_bible",
    "lookup_passage",
    "expand_context",
    "suggest_related_passages",
    "summarize_passage",
    "search_entities",
    "get_entity_relations",
    "get_entity_passages",
    "route_entity_query",
}
```

and:

```python
assert {tool.name for tool in tools} == {
    "search_bible",
    "lookup_passage",
    "expand_context",
    "search_entities",
    "get_entity_passages",
    "route_entity_query",
}
```

- [ ] **Step 2: Run the focused wiring tests to confirm the tool is not wired yet**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/test_mcp_tools.py::test_route_entity_query_handler_trims_query_and_forwards_limit \
  tests/test_mcp_tools.py::test_route_entity_query_handler_routes_relation_and_passage_queries_with_real_services \
  tests/test_related_summary_entities.py::test_create_mcp_server_registers_optional_tools_when_collaborators_are_present \
  -v
```

Expected:

```text
FAILED ... KeyError: 'route_entity_query'
FAILED ... KeyError: 'route_entity_query'
FAILED ... Extra items in the right set: 'route_entity_query'
```

- [ ] **Step 3: Implement the MCP and CLI wiring**

Modify `src/bible_mcp/mcp_server.py` to accept an optional `entity_query_router` in both `build_tool_handlers()` and `create_mcp_server()`, and add a `route_entity_query` handler.

Use these changes:

```python
def build_tool_handlers(
    search_service,
    passage_service,
    related_service,
    summarizer,
    entity_service,
    relation_service=None,
    entity_passage_service=None,
    entity_query_router=None,
):
```

Add the handler:

```python
    def route_entity_query(payload: dict):
        query = _require_text(payload["query"], "query")
        limit = _require_limit(payload.get("limit", 5))
        return entity_query_router.route(query, limit=limit)
```

Register it:

```python
    if entity_query_router is not None:
        handlers["route_entity_query"] = route_entity_query
```

Update the server signature and wiring:

```python
def create_mcp_server(
    search_service,
    passage_service,
    related_service,
    summarizer,
    entity_service,
    relation_service=None,
    entity_passage_service=None,
    entity_query_router=None,
):
```

Pass it through to `build_tool_handlers(...)`, then register the new MCP tool:

```python
    if "route_entity_query" in handlers:

        @mcp.tool()
        def route_entity_query(query: str, limit: int = 5):
            return handlers["route_entity_query"](
                {
                    "query": query,
                    "limit": limit,
                }
            )
```

Modify `src/bible_mcp/cli.py` to instantiate the router only when `entity_service` is available.

Add the import:

```python
from bible_mcp.services.entity_query_router import EntityQueryRouter
```

Update `serve()`:

```python
        if _app_db_supports_optional_study_tools(config):
            related_service = RelatedPassageService(conn, embedder, vector_store)
            entity_service = EntityService(conn)
            summarizer = summarize_passage_text
            relation_service = None
            if _app_db_supports_relation_tools(config):
                relation_service = RelationLookupService(conn, entity_service)
            if _app_db_supports_entity_passage_tools(config):
                entity_passage_service = EntityPassageService(
                    conn,
                    entity_service,
                    passage_service,
                )
            else:
                entity_passage_service = None
            entity_query_router = EntityQueryRouter(
                entity_service,
                relation_service=relation_service,
                entity_passage_service=entity_passage_service,
            )
        else:
            related_service = None
            entity_service = None
            entity_passage_service = None
            entity_query_router = None
            summarizer = None
            relation_service = None
```

Pass it into `create_mcp_server(...)`:

```python
        create_mcp_server(
            search_service,
            passage_service,
            related_service,
            summarizer,
            entity_service,
            relation_service,
            entity_passage_service,
            entity_query_router,
        ).run()
```

- [ ] **Step 4: Re-run focused tests and the full suite**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/test_entity_query_router.py \
  tests/test_mcp_tools.py \
  tests/test_related_summary_entities.py \
  -q
./.venv/bin/python -m pytest -q
```

Expected:

```text
all selected tests PASSED
all tests PASSED
```

- [ ] **Step 5: Commit the MCP and CLI wiring**

Run:

```bash
git add \
  src/bible_mcp/services/entity_query_router.py \
  src/bible_mcp/mcp_server.py \
  src/bible_mcp/cli.py \
  tests/test_entity_query_router.py \
  tests/test_mcp_tools.py \
  tests/test_related_summary_entities.py
git commit -m "feat: expose entity query router over mcp"
```
