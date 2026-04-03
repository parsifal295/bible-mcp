import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from bible_mcp.cli import app
from bible_mcp.db.connection import connect_db
from bible_mcp.db.schema import ensure_schema
from bible_mcp.index.faiss_store import FaissChunkIndex
from bible_mcp.mcp_server import build_tool_handlers, create_mcp_server


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


@dataclass
class FakePassageResult:
    reference: str
    passage_text: str


class FakePassageService:
    def lookup(self, reference: str):
        return FakePassageResult(reference=reference, passage_text="본문")

    def expand_context(self, reference: str, window: int = 2):
        return {"reference": reference, "passage_text": f"{window}절 문맥"}


class FakeEntityService:
    def __init__(self) -> None:
        self.calls = []

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
        return [{"display_name": "아브라함", "entity_type": "people", "slug": "abraham"}]


class FakeRelationService:
    def __init__(self) -> None:
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
        return {
            "resolved_entity": {"display_name": "아브라함", "slug": "abraham"},
            "matches": [],
            "relations": [{"relation_type": "father", "display_name": "이삭", "slug": "isaac"}],
        }


def _write_source_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        create table verses (
            book text not null,
            chapter integer not null,
            verse integer not null,
            text text not null,
            translation text
        )
        """
    )
    conn.commit()
    conn.close()


def _write_app_db(path: Path) -> None:
    conn = connect_db(path)
    ensure_schema(conn)
    conn.close()


def _write_app_db_with_chunk_ids(path: Path, chunk_ids: list[str]) -> None:
    conn = connect_db(path)
    ensure_schema(conn)
    for chunk_id in chunk_ids:
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
                chunk_id,
                "Genesis 1:1",
                "Genesis 1:1",
                "Genesis",
                "1",
                "태초에 하나님이 천지를 창조하시니라",
                5,
                "verse_window",
            ),
        )
    conn.commit()
    conn.close()


def test_search_bible_handler_returns_serializable_payload() -> None:
    handlers = build_tool_handlers(FakeSearchService(), FakePassageService(), None, None, None)
    result = handlers["search_bible"]({"query": "창조", "limit": 3})

    assert result["results"][0]["reference"] == "Genesis 1:1-Genesis 1:3"


def test_lookup_passage_handler_returns_serializable_payload() -> None:
    handlers = build_tool_handlers(FakeSearchService(), FakePassageService(), None, None, None)
    result = handlers["lookup_passage"]({"reference": "Genesis 1:1"})

    assert result == {"reference": "Genesis 1:1", "passage_text": "본문"}


def test_expand_context_handler_delegates_to_passage_service() -> None:
    handlers = build_tool_handlers(FakeSearchService(), FakePassageService(), None, None, None)
    result = handlers["expand_context"]({"reference": "Genesis 1:2", "window": 1})

    assert result["passage_text"] == "1절 문맥"


def test_search_bible_handler_rejects_blank_query() -> None:
    handlers = build_tool_handlers(FakeSearchService(), FakePassageService(), None, None, None)

    with pytest.raises(ValueError, match="query cannot be blank"):
        handlers["search_bible"]({"query": "   ", "limit": 3})


def test_expand_context_handler_rejects_negative_window() -> None:
    handlers = build_tool_handlers(FakeSearchService(), FakePassageService(), None, None, None)

    with pytest.raises(ValueError, match="window must be at least 0"):
        handlers["expand_context"]({"reference": "Genesis 1:2", "window": -1})


def test_search_entities_handler_forwards_optional_filters() -> None:
    entity_service = FakeEntityService()
    handlers = build_tool_handlers(
        FakeSearchService(),
        FakePassageService(),
        None,
        Mock(),
        entity_service,
        None,
    )

    result = handlers["search_entities"](
        {"query": "아브라함", "entity_type": "people", "limit": 2}
    )

    assert entity_service.calls == [
        {
            "query": "아브라함",
            "entity_type": "people",
            "limit": 2,
        }
    ]
    assert result["results"] == [
        {"display_name": "아브라함", "entity_type": "people", "slug": "abraham"}
    ]


def test_search_entities_handler_rejects_invalid_limit() -> None:
    handlers = build_tool_handlers(
        FakeSearchService(),
        FakePassageService(),
        None,
        Mock(),
        FakeEntityService(),
        None,
    )

    with pytest.raises(ValueError, match="limit must be at least 1"):
        handlers["search_entities"]({"query": "아브라함", "limit": 0})


def test_get_entity_relations_handler_forwards_optional_filters() -> None:
    relation_service = FakeRelationService()
    handlers = build_tool_handlers(
        FakeSearchService(),
        FakePassageService(),
        None,
        Mock(),
        FakeEntityService(),
        relation_service,
    )

    result = handlers["get_entity_relations"](
        {
            "query": "아브라함",
            "relation_type": "father",
            "entity_type": "people",
            "direction": "incoming",
            "limit": 3,
        }
    )

    assert relation_service.calls == [
        {
            "query": "아브라함",
            "relation_type": "father",
            "entity_type": "people",
            "direction": "incoming",
            "limit": 3,
        }
    ]
    assert result["relations"] == [
        {"relation_type": "father", "display_name": "이삭", "slug": "isaac"}
    ]


def test_get_entity_relations_handler_rejects_invalid_direction() -> None:
    handlers = build_tool_handlers(
        FakeSearchService(),
        FakePassageService(),
        None,
        Mock(),
        FakeEntityService(),
        FakeRelationService(),
    )

    with pytest.raises(ValueError, match="direction must be 'incoming' or 'outgoing'"):
        handlers["get_entity_relations"]({"query": "아브라함", "direction": "sideways"})


def test_create_mcp_server_registers_expected_tools() -> None:
    mcp = create_mcp_server(FakeSearchService(), FakePassageService(), None, None, None, None)
    tools = asyncio.run(mcp.list_tools())

    assert {tool.name for tool in tools} == {
        "search_bible",
        "lookup_passage",
        "expand_context",
    }


def test_doctor_fails_when_faiss_sidecars_are_missing(tmp_path: Path, monkeypatch) -> None:
    source_db = tmp_path / "source.sqlite"
    app_db = tmp_path / "app.sqlite"
    faiss_path = tmp_path / "chunks.faiss"

    _write_source_db(source_db)
    _write_app_db(app_db)
    FaissChunkIndex(faiss_path).build([("chunk-1", [1.0, 0.0])])
    faiss_path.with_suffix(".json").unlink()
    faiss_path.with_suffix(".meta.json").unlink()

    monkeypatch.setenv("BIBLE_SOURCE_DB", str(source_db))
    monkeypatch.setenv("BIBLE_APP_DB", str(app_db))
    monkeypatch.setenv("BIBLE_FAISS_INDEX", str(faiss_path))

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "FAISS" in result.stdout


def test_doctor_fails_when_faiss_sidecars_are_corrupt(tmp_path: Path, monkeypatch) -> None:
    source_db = tmp_path / "source.sqlite"
    app_db = tmp_path / "app.sqlite"
    faiss_path = tmp_path / "chunks.faiss"

    _write_source_db(source_db)
    _write_app_db(app_db)
    FaissChunkIndex(faiss_path).build([("chunk-1", [1.0, 0.0])])
    faiss_path.with_suffix(".meta.json").write_text('{"mapping_sha256":"bad","count":1}', encoding="utf-8")

    monkeypatch.setenv("BIBLE_SOURCE_DB", str(source_db))
    monkeypatch.setenv("BIBLE_APP_DB", str(app_db))
    monkeypatch.setenv("BIBLE_FAISS_INDEX", str(faiss_path))

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "FAISS mapping integrity mismatch" in result.stdout


def test_doctor_fails_when_faiss_mapping_ids_do_not_match_passage_chunks(
    tmp_path: Path, monkeypatch
) -> None:
    source_db = tmp_path / "source.sqlite"
    app_db = tmp_path / "app.sqlite"
    faiss_path = tmp_path / "chunks.faiss"

    _write_source_db(source_db)
    _write_app_db_with_chunk_ids(app_db, ["chunk-b"])
    FaissChunkIndex(faiss_path).build([("chunk-a", [1.0, 0.0])])

    monkeypatch.setenv("BIBLE_SOURCE_DB", str(source_db))
    monkeypatch.setenv("BIBLE_APP_DB", str(app_db))
    monkeypatch.setenv("BIBLE_FAISS_INDEX", str(faiss_path))

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "passage_chunks" in result.stdout


def test_doctor_allows_same_chunk_ids_in_different_db_row_order(
    tmp_path: Path, monkeypatch
) -> None:
    source_db = tmp_path / "source.sqlite"
    app_db = tmp_path / "app.sqlite"
    faiss_path = tmp_path / "chunks.faiss"

    _write_source_db(source_db)
    _write_app_db_with_chunk_ids(app_db, ["chunk-b", "chunk-a"])
    FaissChunkIndex(faiss_path).build([("chunk-a", [1.0, 0.0]), ("chunk-b", [0.0, 1.0])])

    monkeypatch.setenv("BIBLE_SOURCE_DB", str(source_db))
    monkeypatch.setenv("BIBLE_APP_DB", str(app_db))
    monkeypatch.setenv("BIBLE_FAISS_INDEX", str(faiss_path))

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Doctor check passed" in result.stdout


def test_serve_fails_before_startup_when_app_db_is_missing(tmp_path: Path, monkeypatch) -> None:
    source_db = tmp_path / "source.sqlite"
    faiss_path = tmp_path / "chunks.faiss"
    _write_source_db(source_db)
    FaissChunkIndex(faiss_path).build([("chunk-1", [1.0, 0.0])])

    create_server = Mock()
    monkeypatch.setenv("BIBLE_SOURCE_DB", str(source_db))
    monkeypatch.setenv("BIBLE_APP_DB", str(tmp_path / "missing-app.sqlite"))
    monkeypatch.setenv("BIBLE_FAISS_INDEX", str(faiss_path))
    monkeypatch.setattr("bible_mcp.cli.create_mcp_server", create_server)

    result = CliRunner().invoke(app, ["serve"])

    assert result.exit_code == 1
    assert create_server.call_count == 0


def test_serve_fails_before_startup_when_faiss_sidecars_are_unusable(
    tmp_path: Path, monkeypatch
) -> None:
    source_db = tmp_path / "source.sqlite"
    app_db = tmp_path / "app.sqlite"
    faiss_path = tmp_path / "chunks.faiss"

    _write_source_db(source_db)
    _write_app_db(app_db)
    FaissChunkIndex(faiss_path).build([("chunk-1", [1.0, 0.0])])
    faiss_path.with_suffix(".meta.json").write_text('{"mapping_sha256":"bad","count":1}', encoding="utf-8")

    create_server = Mock()
    monkeypatch.setenv("BIBLE_SOURCE_DB", str(source_db))
    monkeypatch.setenv("BIBLE_APP_DB", str(app_db))
    monkeypatch.setenv("BIBLE_FAISS_INDEX", str(faiss_path))
    monkeypatch.setattr("bible_mcp.cli.create_mcp_server", create_server)

    result = CliRunner().invoke(app, ["serve"])

    assert result.exit_code == 1
    assert create_server.call_count == 0


def test_serve_reports_missing_required_environment_variable(
    tmp_path: Path, monkeypatch
) -> None:
    source_db = tmp_path / "source.sqlite"
    app_db = tmp_path / "app.sqlite"
    faiss_path = tmp_path / "chunks.faiss"

    _write_source_db(source_db)
    _write_app_db(app_db)
    FaissChunkIndex(faiss_path).build([("chunk-1", [1.0, 0.0])])

    monkeypatch.delenv("BIBLE_SOURCE_DB", raising=False)
    monkeypatch.delenv("BIBLE_APP_DB", raising=False)
    monkeypatch.delenv("BIBLE_FAISS_INDEX", raising=False)

    create_server = Mock()
    monkeypatch.setattr("bible_mcp.cli.create_mcp_server", create_server)
    result = CliRunner().invoke(app, ["serve"], env={})

    assert result.exit_code == 1
    assert "BIBLE_SOURCE_DB" in result.stdout
    assert create_server.call_count == 0


def test_index_imports_metadata_before_chunk_and_index_rebuild(
    tmp_path: Path, monkeypatch
) -> None:
    config = Mock()
    config.embeddings.model_name = "test-model"
    config.faiss_index_path = tmp_path / "chunks.faiss"

    call_order: list[str] = []
    fake_conn = object()

    monkeypatch.setattr("bible_mcp.cli.load_config", lambda: config)
    monkeypatch.setattr("bible_mcp.cli.validate_source_database", lambda loaded: call_order.append("validate"))
    monkeypatch.setattr("bible_mcp.cli.connect_db", lambda path: fake_conn)
    monkeypatch.setattr("bible_mcp.cli.ensure_schema", lambda conn: call_order.append("ensure_schema"))
    monkeypatch.setattr("bible_mcp.cli.import_verses", lambda loaded, conn: call_order.append("import_verses"))
    monkeypatch.setattr(
        "bible_mcp.cli.import_metadata_fixtures",
        lambda conn: call_order.append("import_metadata_fixtures"),
    )
    monkeypatch.setattr("bible_mcp.cli.build_chunks", lambda conn: call_order.append("build_chunks"))
    monkeypatch.setattr(
        "bible_mcp.cli.rebuild_fts_indexes",
        lambda conn: call_order.append("rebuild_fts_indexes"),
    )

    class FakeEmbedder:
        def __init__(self, model_name: str) -> None:
            call_order.append(f"embedder:{model_name}")

    class FakeVectorStore:
        def __init__(self, path: Path) -> None:
            call_order.append(f"vector_store:{path.name}")

    monkeypatch.setattr("bible_mcp.cli.SentenceTransformerEmbedder", FakeEmbedder)
    monkeypatch.setattr("bible_mcp.cli.FaissChunkIndex", FakeVectorStore)
    monkeypatch.setattr(
        "bible_mcp.cli.index_chunk_embeddings",
        lambda conn, embedder, vector_store: call_order.append("index_chunk_embeddings"),
    )

    result = CliRunner().invoke(app, ["index"])

    assert result.exit_code == 0
    assert call_order == [
        "validate",
        "ensure_schema",
        "import_verses",
        "import_metadata_fixtures",
        "build_chunks",
        "rebuild_fts_indexes",
        "embedder:test-model",
        "vector_store:chunks.faiss",
        "index_chunk_embeddings",
    ]
