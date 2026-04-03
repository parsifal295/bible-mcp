import sqlite3
from pathlib import Path

from bible_mcp.config import AppConfig, SourceBibleConfig
from bible_mcp.db.connection import connect_db
from bible_mcp.db.schema import ensure_schema
from bible_mcp.ingest.importer import import_verses


def test_import_verses_copies_source_rows_into_normalized_table(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    app_path = tmp_path / "app.sqlite"

    source = sqlite3.connect(source_path)
    source.execute(
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
    source.executemany(
        "insert into verses(book, chapter, verse, text, translation) values (?, ?, ?, ?, ?)",
        [
            ("Genesis", 1, 1, "태초에 하나님이 천지를 창조하시니라", "KOR"),
            ("Genesis", 1, 2, "땅이 혼돈하고 공허하며", "KOR"),
        ],
    )
    source.commit()
    source.close()

    config = AppConfig(
        source=SourceBibleConfig(path=source_path, table="verses"),
        app_db_path=app_path,
        faiss_index_path=tmp_path / "index.faiss",
    )

    conn = connect_db(config.app_db_path)
    ensure_schema(conn)
    import_verses(config, conn)

    rows = [
        tuple(row)
        for row in conn.execute(
            "select reference, text from verses order by book_order, chapter, verse"
        ).fetchall()
    ]

    assert rows == [
        ("Genesis 1:1", "태초에 하나님이 천지를 창조하시니라"),
        ("Genesis 1:2", "땅이 혼돈하고 공허하며"),
    ]


def test_import_verses_accepts_source_rows_without_translation_column(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    app_path = tmp_path / "app.sqlite"

    source = sqlite3.connect(source_path)
    source.execute(
        """
        create table verses (
            book text not null,
            chapter integer not null,
            verse integer not null,
            text text not null
        )
        """
    )
    source.execute(
        "insert into verses(book, chapter, verse, text) values (?, ?, ?, ?)",
        ("Genesis", 1, 1, "태초에 하나님이 천지를 창조하시니라"),
    )
    source.commit()
    source.close()

    config = AppConfig(
        source=SourceBibleConfig(path=source_path, table="verses"),
        app_db_path=app_path,
        faiss_index_path=tmp_path / "index.faiss",
    )

    conn = connect_db(config.app_db_path)
    ensure_schema(conn)
    import_verses(config, conn)

    rows = [
        tuple(row)
        for row in conn.execute(
            "select reference, text, translation from verses order by book_order, chapter, verse"
        ).fetchall()
    ]

    assert rows == [
        ("Genesis 1:1", "태초에 하나님이 천지를 창조하시니라", None),
    ]


def test_import_verses_rejects_unknown_book_names(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    app_path = tmp_path / "app.sqlite"

    source = sqlite3.connect(source_path)
    source.execute(
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
    source.execute(
        "insert into verses(book, chapter, verse, text, translation) values (?, ?, ?, ?, ?)",
        ("NotABook", 1, 1, "unexpected", "KOR"),
    )
    source.commit()
    source.close()

    config = AppConfig(
        source=SourceBibleConfig(path=source_path, table="verses"),
        app_db_path=app_path,
        faiss_index_path=tmp_path / "index.faiss",
    )

    conn = connect_db(config.app_db_path)
    ensure_schema(conn)

    try:
        import_verses(config, conn)
    except ValueError as exc:
        assert "NotABook" in str(exc)
    else:
        raise AssertionError("expected import_verses to reject unknown book names")


def test_import_verses_rolls_back_partial_work_on_failure(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    app_path = tmp_path / "app.sqlite"

    source = sqlite3.connect(source_path)
    source.execute(
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
    source.executemany(
        "insert into verses(book, chapter, verse, text, translation) values (?, ?, ?, ?, ?)",
        [
            ("Genesis", 1, 1, "태초에 하나님이 천지를 창조하시니라", "KOR"),
            ("NotABook", 1, 1, "unexpected", "KOR"),
        ],
    )
    source.commit()
    source.close()

    config = AppConfig(
        source=SourceBibleConfig(path=source_path, table="verses"),
        app_db_path=app_path,
        faiss_index_path=tmp_path / "index.faiss",
    )

    conn = connect_db(config.app_db_path)
    ensure_schema(conn)

    try:
        import_verses(config, conn)
    except ValueError:
        pass
    else:
        raise AssertionError("expected import_verses to fail on the unknown book")

    rows = conn.execute("select reference, text from verses").fetchall()
    assert rows == []
