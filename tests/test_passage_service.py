from pathlib import Path

from bible_mcp.db.connection import connect_db
from bible_mcp.db.schema import ensure_schema
from bible_mcp.query.parser import parse_reference
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


def test_lookup_chapter_only_returns_parseable_actual_verse_range(tmp_path: Path) -> None:
    db_path = tmp_path / "app.sqlite"
    conn = connect_db(db_path)
    ensure_schema(conn)
    conn.executemany(
        """
        insert into verses(translation, book, book_order, chapter, verse, reference, testament, text)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("KOR", "Exodus", 2, 3, 14, "Exodus 3:14", "OT", "하나님이 모세에게 이르시되 나는 스스로 있는 자이니라"),
            ("KOR", "Exodus", 2, 3, 15, "Exodus 3:15", "OT", "너는 이스라엘 자손에게 이같이 이르기를"),
        ],
    )
    conn.commit()

    service = PassageService(conn)
    result = service.lookup("출 3장")

    assert result.reference == "Exodus 3:14-15"
    assert parse_reference(result.reference) is not None


def test_lookup_returns_actual_verse_range_when_requested_bounds_are_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "app.sqlite"
    conn = connect_db(db_path)
    ensure_schema(conn)
    conn.executemany(
        """
        insert into verses(translation, book, book_order, chapter, verse, reference, testament, text)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("KOR", "1 John", 62, 1, 9, "1 John 1:9", "NT", "만일 우리가 우리 죄를 자백하면"),
            ("KOR", "1 John", 62, 1, 10, "1 John 1:10", "NT", "만일 우리가 범죄하지 아니하였다 하면"),
        ],
    )
    conn.commit()

    service = PassageService(conn)
    result = service.lookup("1 John 1:8-10")

    assert result.reference == "1 John 1:9-10"
    assert parse_reference(result.reference) is not None


def test_expand_context_clamps_reported_range_to_actual_returned_verses(tmp_path: Path) -> None:
    db_path = tmp_path / "app.sqlite"
    conn = connect_db(db_path)
    ensure_schema(conn)
    conn.executemany(
        """
        insert into verses(translation, book, book_order, chapter, verse, reference, testament, text)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("KOR", "Genesis", 1, 1, 2, "Genesis 1:2", "OT", "땅이 혼돈하고 공허하며"),
            ("KOR", "Genesis", 1, 1, 3, "Genesis 1:3", "OT", "하나님이 이르시되 빛이 있으라 하시니"),
        ],
    )
    conn.commit()

    service = PassageService(conn)
    result = service.expand_context("창 1:3", window=5)

    assert result.reference == "Genesis 1:2-3"
    assert parse_reference(result.reference) is not None
