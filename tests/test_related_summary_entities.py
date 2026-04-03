import asyncio
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from bible_mcp.cli import app
from bible_mcp.config import AppConfig, SourceBibleConfig
from bible_mcp.mcp_server import build_tool_handlers
from bible_mcp.mcp_server import create_mcp_server
from bible_mcp.services.entity_query_router import EntityQueryRouter
from bible_mcp.services.related_service import RelatedPassageService
from bible_mcp.services.entity_service import EntityService
from bible_mcp.services.entity_passage_service import EntityPassageService
from bible_mcp.services.relation_service import RelationLookupService
from bible_mcp.services.summarizer import summarize_passage_text


def _write_base_runtime_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        create table verses (
            id integer primary key,
            translation text,
            book text not null,
            book_order integer not null,
            chapter integer not null,
            verse integer not null,
            reference text not null unique,
            testament text,
            text text not null
        );

        create table passage_chunks (
            id integer primary key,
            chunk_id text not null unique,
            start_ref text not null,
            end_ref text not null,
            book text not null,
            chapter_range text not null,
            text text not null,
            token_count integer not null,
            chunk_strategy text not null
        );

        create virtual table passage_chunks_fts using fts5(
            chunk_id,
            text,
            content='',
            tokenize='unicode61'
        );
        """
    )
    conn.commit()
    conn.close()


def _write_optional_study_db(path: Path, include_entity_verse_links: bool) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        create table verses (
            id integer primary key,
            translation text,
            book text not null,
            book_order integer not null,
            chapter integer not null,
            verse integer not null,
            reference text not null unique,
            testament text,
            text text not null
        );

        create table passage_chunks (
            id integer primary key,
            chunk_id text not null unique,
            start_ref text not null,
            end_ref text not null,
            book text not null,
            chapter_range text not null,
            text text not null,
            token_count integer not null,
            chunk_strategy text not null
        );

        create virtual table passage_chunks_fts using fts5(
            chunk_id,
            text,
            content='',
            tokenize='unicode61'
        );

        create table people (
            id integer primary key,
            slug text not null unique,
            display_name text not null,
            description text
        );

        create table entity_aliases (
            id integer primary key,
            entity_type text not null,
            entity_slug text not null,
            alias text not null
        );
        """
    )
    if include_entity_verse_links:
        conn.execute(
            """
            create table entity_verse_links (
                id integer primary key,
                entity_type text not null,
                entity_slug text not null,
                reference text not null
            )
            """
        )
    conn.commit()
    conn.close()


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


def test_serve_omits_optional_tools_when_entity_tables_are_missing(
    tmp_path, monkeypatch
) -> None:
    app_db_path = tmp_path / "app.sqlite"
    _write_base_runtime_db(app_db_path)

    config = AppConfig(
        source=SourceBibleConfig(path=tmp_path / "source.sqlite", table="verses"),
        app_db_path=app_db_path,
        faiss_index_path=tmp_path / "chunks.faiss",
    )

    captured = {}

    class FakeEmbedder:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _text in texts]

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

    monkeypatch.setattr("bible_mcp.cli.load_config", lambda: config)
    monkeypatch.setattr("bible_mcp.cli.validate_runtime_installation", lambda config: object())
    monkeypatch.setattr("bible_mcp.cli.SentenceTransformerEmbedder", FakeEmbedder)
    monkeypatch.setattr("bible_mcp.cli.create_mcp_server", fake_create_mcp_server)

    result = CliRunner().invoke(app, ["serve"])

    assert result.exit_code == 0
    assert captured["related_service"] is None
    assert captured["summarizer"] is None
    assert captured["entity_service"] is None
    assert captured["relation_service"] is None
    assert captured["entity_passage_service"] is None
    assert captured["entity_query_router"] is None


def test_serve_omits_entity_passage_service_when_entity_verse_links_are_missing(
    tmp_path, monkeypatch
) -> None:
    app_db_path = tmp_path / "app.sqlite"
    _write_optional_study_db(app_db_path, include_entity_verse_links=False)

    config = AppConfig(
        source=SourceBibleConfig(path=tmp_path / "source.sqlite", table="verses"),
        app_db_path=app_db_path,
        faiss_index_path=tmp_path / "chunks.faiss",
    )

    captured = {}

    class FakeEmbedder:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _text in texts]

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

    monkeypatch.setattr("bible_mcp.cli.load_config", lambda: config)
    monkeypatch.setattr("bible_mcp.cli.validate_runtime_installation", lambda config: object())
    monkeypatch.setattr("bible_mcp.cli.SentenceTransformerEmbedder", FakeEmbedder)
    monkeypatch.setattr("bible_mcp.cli.create_mcp_server", fake_create_mcp_server)

    result = CliRunner().invoke(app, ["serve"])

    assert result.exit_code == 0
    assert captured["related_service"] is not None
    assert captured["summarizer"] is summarize_passage_text
    assert isinstance(captured["entity_service"], EntityService)
    assert captured["relation_service"] is None
    assert captured["entity_passage_service"] is None
    assert isinstance(captured["entity_query_router"], EntityQueryRouter)


def test_serve_wires_relation_lookup_service_when_optional_tables_are_present(
    tmp_path, monkeypatch
) -> None:
    from bible_mcp.db.connection import connect_db
    from bible_mcp.db.schema import ensure_schema

    app_db_path = tmp_path / "app.sqlite"
    conn = connect_db(app_db_path)
    ensure_schema(conn)
    conn.close()

    config = AppConfig(
        source=SourceBibleConfig(path=tmp_path / "source.sqlite", table="verses"),
        app_db_path=app_db_path,
        faiss_index_path=tmp_path / "chunks.faiss",
    )

    captured = {}

    class FakeEmbedder:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _text in texts]

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

    monkeypatch.setattr("bible_mcp.cli.load_config", lambda: config)
    monkeypatch.setattr("bible_mcp.cli.validate_runtime_installation", lambda config: object())
    monkeypatch.setattr("bible_mcp.cli.SentenceTransformerEmbedder", FakeEmbedder)
    monkeypatch.setattr("bible_mcp.cli.create_mcp_server", fake_create_mcp_server)

    result = CliRunner().invoke(app, ["serve"])

    assert result.exit_code == 0
    assert isinstance(captured["related_service"], RelatedPassageService)
    assert captured["summarizer"] is summarize_passage_text
    assert isinstance(captured["entity_service"], EntityService)
    assert isinstance(captured["relation_service"], RelationLookupService)
    assert isinstance(captured["entity_passage_service"], EntityPassageService)
    assert isinstance(captured["entity_query_router"], EntityQueryRouter)


def test_create_mcp_server_registers_optional_tools_when_collaborators_are_present() -> None:
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
        def search(self, query: str, entity_type: str | None = None, limit: int = 5):
            return [{"display_name": "아브라함"}]

    class FakeEntityPassageService:
        def lookup(
            self,
            query: str,
            entity_type: str | None = None,
            limit: int = 5,
        ):
            return {"resolved_entity": None, "matches": [], "passages": []}

    class FakeRelationService:
        def lookup(
            self,
            query: str,
            relation_type: str | None = None,
            entity_type: str | None = None,
            direction: str = "outgoing",
            limit: int = 5,
        ):
            return {"resolved_entity": None, "matches": [], "relations": []}

    class FakeEntityQueryRouter:
        def route(self, query: str, limit: int = 5):
            return {"intent": "entity_search", "parsed": {"query": query}, "result": {"results": []}, "error": None}

    mcp = create_mcp_server(
        FakeSearchService(),
        FakePassageService(),
        FakeRelatedService(),
        summarize_passage_text,
        FakeEntityService(),
        FakeRelationService(),
        FakeEntityPassageService(),
        FakeEntityQueryRouter(),
    )
    tools = asyncio.run(mcp.list_tools())

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


def test_create_mcp_server_registers_entity_search_without_relation_lookup() -> None:
    class FakeSearchService:
        def search(self, query: str, limit: int = 5):
            return []

    class FakePassageService:
        def lookup(self, reference: str):
            return {"reference": reference, "passage_text": "본문"}

        def expand_context(self, reference: str, window: int = 2):
            return {"reference": reference, "passage_text": "문맥"}

    class FakeEntityService:
        def search(self, query: str, entity_type: str | None = None, limit: int = 5):
            return [{"display_name": "아브라함"}]

    class FakeEntityPassageService:
        def lookup(
            self,
            query: str,
            entity_type: str | None = None,
            limit: int = 5,
        ):
            return {"resolved_entity": None, "matches": [], "passages": []}

    class FakeEntityQueryRouter:
        def route(self, query: str, limit: int = 5):
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
                "result": {"results": []},
                "error": None,
            }

    mcp = create_mcp_server(
        FakeSearchService(),
        FakePassageService(),
        None,
        None,
        FakeEntityService(),
        None,
        FakeEntityPassageService(),
        FakeEntityQueryRouter(),
    )
    tools = asyncio.run(mcp.list_tools())

    assert {tool.name for tool in tools} == {
        "search_bible",
        "lookup_passage",
        "expand_context",
        "search_entities",
        "get_entity_passages",
        "route_entity_query",
    }


def test_related_passage_service_skips_missing_chunk_rows(tmp_path) -> None:
    from bible_mcp.db.connection import connect_db
    from bible_mcp.db.schema import ensure_schema

    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)
    conn.execute(
        """
        insert into passage_chunks(
            chunk_id,
            start_ref,
            end_ref,
            book,
            chapter_range,
            text,
            token_count,
            chunk_strategy
        )
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "chunk-a",
            "Genesis 1:1",
            "Genesis 1:3",
            "Genesis",
            "1",
            "태초에 하나님이 천지를 창조하시니라",
            5,
            "verse_window",
        ),
    )
    conn.commit()

    class FakeEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _text in texts]

    class FakeVectorIndex:
        def search(self, query_vector: list[float], limit: int = 5):
            return [("missing-chunk", 0.99), ("chunk-a", 0.88)]

    service = RelatedPassageService(conn, FakeEmbedder(), FakeVectorIndex())
    results = service.suggest("태초", limit=2)

    assert len(results) == 1
    assert results[0]["reference"] == "Genesis 1:1-Genesis 1:3"
    assert results[0]["passage_text"] == "태초에 하나님이 천지를 창조하시니라"
    assert results[0]["score"] == 0.88
