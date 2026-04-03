import json
from pathlib import Path

from bible_mcp.db.connection import connect_db
from bible_mcp.db.schema import ensure_schema
from bible_mcp.index.fts import rebuild_fts_indexes
from bible_mcp.ingest.chunker import build_chunks
from bible_mcp.services.search_service import SearchService


class FakeEmbedder:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class FakeVectorIndex:
    def search(self, _vector, limit: int = 5):
        return [
            ("Genesis 1:1-Genesis 1:3", 0.90),
            ("Hebrews 11:1-Hebrews 11:1", 0.88),
            ("Romans 8:28-Romans 8:28", 0.87),
        ][:limit]


def test_golden_queries_return_expected_reference(tmp_path: Path) -> None:
    fixture = Path("tests/golden_queries.json")
    payload = json.loads(fixture.read_text(encoding="utf-8"))

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
            ("KOR", "Hebrews", 58, 11, 1, "Hebrews 11:1", "NT", "믿음은 바라는 것들의 실상이요 보이지 않는 것들의 증거니"),
            ("KOR", "Romans", 45, 8, 28, "Romans 8:28", "NT", "하나님을 사랑하는 자 곧 그의 뜻대로 부르심을 입은 자들에게는"),
        ],
    )
    conn.commit()
    build_chunks(conn, max_verses=3, stride=1)
    rebuild_fts_indexes(conn)

    service = SearchService(conn, FakeEmbedder(), FakeVectorIndex())

    for item in payload:
        results = service.search(item["query"], limit=3)
        references = [result.reference for result in results]
        assert any(reference in item["expected_any_reference"] for reference in references)
