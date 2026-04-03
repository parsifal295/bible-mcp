import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock

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


def test_create_mcp_server_registers_expected_tools() -> None:
    mcp = create_mcp_server(FakeSearchService(), FakePassageService(), None, None, None)
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
