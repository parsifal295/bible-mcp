from pathlib import Path

from bible_mcp.db.connection import connect_db
from bible_mcp.db.schema import ensure_schema
from bible_mcp.index.fts import rebuild_fts_indexes
from bible_mcp.ingest.chunker import build_chunks
from bible_mcp.query.context import expand_chunk_context
from bible_mcp.services.search_service import SearchService


class FakeVectorIndex:
    def search(self, _vector, limit: int = 5):
        return [("Genesis 1:1-Genesis 1:3", 0.91)][:limit]


class FakeEmbedder:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


def test_search_combines_keyword_and_semantic_hits(tmp_path: Path) -> None:
    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)
    conn.executemany(
        """
        insert into verses(translation, book, book_order, chapter, verse, reference, testament, text)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("KOR", "Genesis", 1, 1, 1, "Genesis 1:1", "OT", "태초에 하나님이 천지를 창조하시니라"),
            ("KOR", "Genesis", 1, 1, 2, "Genesis 1:2", "OT", "땅이 혼돈하고 공허하며"),
            ("KOR", "Genesis", 1, 1, 3, "Genesis 1:3", "OT", "하나님이 이르시되 빛이 있으라 하시니"),
        ],
    )
    conn.commit()
    build_chunks(conn, max_verses=3, stride=3)
    rebuild_fts_indexes(conn)

    service = SearchService(conn, FakeEmbedder(), FakeVectorIndex())
    results = service.search("천지를", limit=3)

    assert results[0].reference == "Genesis 1:1-Genesis 1:3"
    assert "keyword" in results[0].match_reasons
    assert "semantic" in results[0].match_reasons


def test_expand_chunk_context_handles_cross_chapter_chunks(tmp_path: Path) -> None:
    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)
    conn.executemany(
        """
        insert into verses(translation, book, book_order, chapter, verse, reference, testament, text)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("KOR", "Genesis", 1, 1, 1, "Genesis 1:1", "OT", "태초에 하나님이 천지를 창조하시니라"),
            ("KOR", "Genesis", 1, 1, 2, "Genesis 1:2", "OT", "땅이 혼돈하고 공허하며"),
            ("KOR", "Genesis", 1, 2, 1, "Genesis 2:1", "OT", "천지와 만물이 다 이루어지니라"),
        ],
    )
    conn.commit()

    rows = expand_chunk_context(conn, "Genesis 1:2", "Genesis 2:1", window=0)

    assert [row["reference"] for row in rows] == [
        "Genesis 1:2",
        "Genesis 2:1",
    ]
