from pathlib import Path

from bible_mcp.db.connection import connect_db
from bible_mcp.db.schema import ensure_schema
from bible_mcp.services.passage_service import PassageService


def test_lookup_passage_returns_exact_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "app.sqlite"
    conn = connect_db(db_path)
    ensure_schema(conn)
    conn.executemany(
        """
        insert into verses(translation, book, book_order, chapter, verse, reference, testament, text)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("KOR", "Genesis", 1, 1, 1, "Genesis 1:1", "OT", "태초에 하나님이 천지를 창조하시니라"),
            ("KOR", "Genesis", 1, 1, 2, "Genesis 1:2", "OT", "땅이 혼돈하고 공허하며"),
        ],
    )
    conn.commit()

    service = PassageService(conn)
    result = service.lookup("Genesis 1:1-2")

    assert result.reference == "Genesis 1:1-2"
    assert "천지를" in result.passage_text


def test_expand_context_returns_neighboring_verses(tmp_path: Path) -> None:
    db_path = tmp_path / "app.sqlite"
    conn = connect_db(db_path)
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

    service = PassageService(conn)
    result = service.expand_context("Genesis 1:2", window=1)

    assert result.reference == "Genesis 1:1-3"
    assert "빛이 있으라" in result.passage_text
