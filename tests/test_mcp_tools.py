from bible_mcp.mcp_server import build_tool_handlers


class FakeSearchService:
    def search(self, query: str, limit: int = 5):
        return [
            {
                "reference": "Genesis 1:1-Genesis 1:3",
                "passage_text": "태초에 하나님이 천지를 창조하시니라",
                "score": 0.99,
                "match_reasons": ["keyword", "semantic"],
                "related_entities": [],
            }
        ]


class FakePassageService:
    def lookup(self, reference: str):
        return {"reference": reference, "passage_text": "본문"}

    def expand_context(self, reference: str, window: int = 2):
        return {"reference": reference, "passage_text": f"{window}절 문맥"}


def test_search_bible_handler_returns_serializable_payload() -> None:
    handlers = build_tool_handlers(FakeSearchService(), FakePassageService(), None, None, None)
    result = handlers["search_bible"]({"query": "창조", "limit": 3})

    assert result["results"][0]["reference"] == "Genesis 1:1-Genesis 1:3"


def test_expand_context_handler_delegates_to_passage_service() -> None:
    handlers = build_tool_handlers(FakeSearchService(), FakePassageService(), None, None, None)
    result = handlers["expand_context"]({"reference": "Genesis 1:2", "window": 1})

    assert result["passage_text"] == "1절 문맥"
