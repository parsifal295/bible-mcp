from mcp.server.fastmcp import FastMCP


def _to_payload(value):
    if hasattr(value, "__dict__"):
        return value.__dict__
    return value


def build_tool_handlers(search_service, passage_service, related_service, summarizer, entity_service):
    def search_bible(payload: dict):
        query = payload["query"]
        limit = int(payload.get("limit", 5))
        results = search_service.search(query, limit=limit)
        return {"results": [_to_payload(result) for result in results]}

    def lookup_passage(payload: dict):
        reference = payload["reference"]
        result = passage_service.lookup(reference)
        return _to_payload(result)

    def expand_context(payload: dict):
        reference = payload["reference"]
        window = int(payload.get("window", 2))
        result = passage_service.expand_context(reference, window=window)
        return _to_payload(result)

    return {
        "search_bible": search_bible,
        "lookup_passage": lookup_passage,
        "expand_context": expand_context,
    }


def create_mcp_server(search_service, passage_service, related_service, summarizer, entity_service):
    mcp = FastMCP("bible-mcp")
    handlers = build_tool_handlers(search_service, passage_service, related_service, summarizer, entity_service)

    @mcp.tool()
    def search_bible(query: str, limit: int = 5):
        return handlers["search_bible"]({"query": query, "limit": limit})

    @mcp.tool()
    def lookup_passage(reference: str):
        return handlers["lookup_passage"]({"reference": reference})

    @mcp.tool()
    def expand_context(reference: str, window: int = 2):
        return handlers["expand_context"]({"reference": reference, "window": window})

    return mcp
