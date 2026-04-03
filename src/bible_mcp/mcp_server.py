from mcp.server.fastmcp import FastMCP

from bible_mcp.domain.metadata import DEFAULT_RELATION_DIRECTION, RELATION_DIRECTIONS


def _to_payload(value):
    if hasattr(value, "__dict__"):
        return value.__dict__
    return value


def _require_text(value, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} cannot be blank")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} cannot be blank")
    return text


def _optional_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _require_limit(value, field_name: str = "limit") -> int:
    limit = int(value)
    if limit < 1:
        raise ValueError(f"{field_name} must be at least 1")
    return limit


def _require_window(value) -> int:
    window = int(value)
    if window < 0:
        raise ValueError("window must be at least 0")
    return window


def _require_direction(value, field_name: str = "direction") -> str:
    direction = _require_text(value, field_name)
    if direction not in RELATION_DIRECTIONS:
        raise ValueError(f"{field_name} must be 'incoming' or 'outgoing'")
    return direction


def build_tool_handlers(
    search_service,
    passage_service,
    related_service,
    summarizer,
    entity_service,
    relation_service=None,
):
    def search_bible(payload: dict):
        query = _require_text(payload["query"], "query")
        limit = _require_limit(payload.get("limit", 5))
        results = search_service.search(query, limit=limit)
        return {"results": [_to_payload(result) for result in results]}

    def lookup_passage(payload: dict):
        reference = _require_text(payload["reference"], "reference")
        result = passage_service.lookup(reference)
        return _to_payload(result)

    def expand_context(payload: dict):
        reference = _require_text(payload["reference"], "reference")
        window = _require_window(payload.get("window", 2))
        result = passage_service.expand_context(reference, window=window)
        return _to_payload(result)

    def suggest_related_passages(payload: dict):
        source_text = _require_text(payload["text"], "text")
        limit = _require_limit(payload.get("limit", 5))
        results = related_service.suggest(source_text, limit=limit)
        return {"results": [_to_payload(result) for result in results]}

    def summarize_passage(payload: dict):
        text = _require_text(payload["text"], "text")
        return summarizer(text)

    def search_entities(payload: dict):
        query = _require_text(payload["query"], "query")
        entity_type = _optional_text(payload.get("entity_type"))
        limit = _require_limit(payload.get("limit", 5))
        results = entity_service.search(query, entity_type=entity_type, limit=limit)
        return {"results": [_to_payload(result) for result in results]}

    def get_entity_relations(payload: dict):
        query = _require_text(payload["query"], "query")
        relation_type = _optional_text(payload.get("relation_type"))
        entity_type = _optional_text(payload.get("entity_type"))
        direction = _require_direction(payload.get("direction", DEFAULT_RELATION_DIRECTION))
        limit = _require_limit(payload.get("limit", 5))
        return relation_service.lookup(
            query,
            relation_type=relation_type,
            entity_type=entity_type,
            direction=direction,
            limit=limit,
        )

    handlers = {
        "search_bible": search_bible,
        "lookup_passage": lookup_passage,
        "expand_context": expand_context,
    }

    if related_service is not None:
        handlers["suggest_related_passages"] = suggest_related_passages

    if summarizer is not None:
        handlers["summarize_passage"] = summarize_passage

    if entity_service is not None:
        handlers["search_entities"] = search_entities

    if relation_service is not None:
        handlers["get_entity_relations"] = get_entity_relations

    return handlers


def create_mcp_server(
    search_service,
    passage_service,
    related_service,
    summarizer,
    entity_service,
    relation_service=None,
):
    mcp = FastMCP("bible-mcp")
    handlers = build_tool_handlers(
        search_service,
        passage_service,
        related_service,
        summarizer,
        entity_service,
        relation_service,
    )

    @mcp.tool()
    def search_bible(query: str, limit: int = 5):
        return handlers["search_bible"]({"query": query, "limit": limit})

    @mcp.tool()
    def lookup_passage(reference: str):
        return handlers["lookup_passage"]({"reference": reference})

    @mcp.tool()
    def expand_context(reference: str, window: int = 2):
        return handlers["expand_context"]({"reference": reference, "window": window})

    if "suggest_related_passages" in handlers:

        @mcp.tool()
        def suggest_related_passages(text: str, limit: int = 5):
            return handlers["suggest_related_passages"]({"text": text, "limit": limit})

    if "summarize_passage" in handlers:

        @mcp.tool()
        def summarize_passage(text: str):
            return handlers["summarize_passage"]({"text": text})

    if "search_entities" in handlers:

        @mcp.tool()
        def search_entities(
            query: str,
            entity_type: str | None = None,
            limit: int = 5,
        ):
            return handlers["search_entities"](
                {
                    "query": query,
                    "entity_type": entity_type,
                    "limit": limit,
                }
            )

    if "get_entity_relations" in handlers:

        @mcp.tool()
        def get_entity_relations(
            query: str,
            relation_type: str | None = None,
            entity_type: str | None = None,
            direction: str = DEFAULT_RELATION_DIRECTION,
            limit: int = 5,
        ):
            return handlers["get_entity_relations"](
                {
                    "query": query,
                    "relation_type": relation_type,
                    "entity_type": entity_type,
                    "direction": direction,
                    "limit": limit,
                }
            )

    return mcp
