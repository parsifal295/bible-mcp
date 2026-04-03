from bible_mcp.mcp_server import build_tool_handlers
from bible_mcp.services.entity_service import EntityService
from bible_mcp.services.summarizer import summarize_passage_text


def test_summarize_passage_text_extracts_keywords() -> None:
    summary = summarize_passage_text("믿음은 바라는 것들의 실상이요 보이지 않는 것들의 증거니")
    assert "믿음" in summary["keywords"]


def test_entity_service_matches_aliases(tmp_path) -> None:
    from bible_mcp.db.connection import connect_db
    from bible_mcp.db.schema import ensure_schema

    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)
    conn.execute("insert into people(slug, display_name, description) values ('abraham', '아브라함', '족장')")
    conn.execute(
        "insert into entity_aliases(entity_type, entity_slug, alias) values ('people', 'abraham', 'Abram')"
    )
    conn.commit()

    service = EntityService(conn)
    matches = service.search("Abram")

    assert matches[0]["display_name"] == "아브라함"


def test_mcp_handler_exposes_summary_tool() -> None:
    class FakeSearchService:
        def search(self, query: str, limit: int = 5):
            return []

    class FakePassageService:
        def lookup(self, reference: str):
            return {"reference": reference, "passage_text": "본문"}

        def expand_context(self, reference: str, window: int = 2):
            return {"reference": reference, "passage_text": "문맥"}

    class FakeRelatedService:
        def suggest(self, source_text: str, limit: int = 5):
            return [{"reference": "Romans 8:28", "passage_text": "모든 것이 합력하여", "score": 0.88}]

    class FakeEntityService:
        def search(self, query: str):
            return [{"display_name": "아브라함"}]

    handlers = build_tool_handlers(
        FakeSearchService(),
        FakePassageService(),
        FakeRelatedService(),
        summarize_passage_text,
        FakeEntityService(),
    )

    summary = handlers["summarize_passage"]({"text": "믿음은 바라는 것들의 실상이요"})
    related = handlers["suggest_related_passages"]({"text": "믿음", "limit": 1})
    entities = handlers["search_entities"]({"query": "아브라함"})

    assert "믿음" in summary["keywords"]
    assert related["results"][0]["reference"] == "Romans 8:28"
    assert entities["results"][0]["display_name"] == "아브라함"
