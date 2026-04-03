from pathlib import Path

import sqlite3

from bible_mcp.config import AppConfig, SourceBibleConfig
from bible_mcp.db.connection import connect_db
from bible_mcp.db.schema import ensure_schema
from bible_mcp.ingest.chunker import build_chunks
from bible_mcp.ingest.importer import import_verses, reset_indexes
from bible_mcp.index.fts import rebuild_fts_indexes, search_keyword


def test_build_chunks_groups_adjacent_verses(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    app_path = tmp_path / "app.sqlite"

    source = sqlite3.connect(source_path)
    source.execute(
        "create table verses (book text, chapter integer, verse integer, text text, translation text)"
    )
    source.executemany(
        "insert into verses values (?, ?, ?, ?, ?)",
        [
            ("Genesis", 1, 1, "태초에 하나님이 천지를 창조하시니라", "KOR"),
            ("Genesis", 1, 2, "땅이 혼돈하고 공허하며", "KOR"),
            ("Genesis", 1, 3, "하나님이 이르시되 빛이 있으라 하시니", "KOR"),
            ("Genesis", 1, 4, "빛이 하나님이 보시기에 좋았더라", "KOR"),
        ],
    )
    source.commit()
    source.close()

    config = AppConfig(
        source=SourceBibleConfig(path=source_path, table="verses"),
        app_db_path=app_path,
        faiss_index_path=tmp_path / "index.faiss",
    )

    conn = connect_db(app_path)
    ensure_schema(conn)
    import_verses(config, conn)

    chunks = build_chunks(conn, max_verses=3, stride=2)
    assert chunks[0].start_ref == "Genesis 1:1"
    assert chunks[0].end_ref == "Genesis 1:3"


def test_build_chunks_keeps_trailing_verses_at_book_boundary(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    app_path = tmp_path / "app.sqlite"

    source = sqlite3.connect(source_path)
    source.execute(
        "create table verses (book text, chapter integer, verse integer, text text, translation text)"
    )
    source.executemany(
        "insert into verses values (?, ?, ?, ?, ?)",
        [
            ("Genesis", 1, 1, "태초에 하나님이 천지를 창조하시니라", "KOR"),
            ("Genesis", 1, 2, "땅이 혼돈하고 공허하며", "KOR"),
            ("Exodus", 1, 1, "야곱과 함께 각기 가족을 데리고 이집트에 왔으니", "KOR"),
            ("Exodus", 1, 2, "르우벤과 시므온과 레위와 유다", "KOR"),
        ],
    )
    source.commit()
    source.close()

    config = AppConfig(
        source=SourceBibleConfig(path=source_path, table="verses"),
        app_db_path=app_path,
        faiss_index_path=tmp_path / "index.faiss",
    )

    conn = connect_db(app_path)
    ensure_schema(conn)
    import_verses(config, conn)

    chunks = build_chunks(conn, max_verses=3, stride=2)
    chunk_refs = {(chunk.start_ref, chunk.end_ref) for chunk in chunks}

    assert ("Genesis 1:1", "Genesis 1:2") in chunk_refs
    assert ("Exodus 1:1", "Exodus 1:2") in chunk_refs


def test_search_keyword_returns_matching_reference(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    app_path = tmp_path / "app.sqlite"

    source = sqlite3.connect(source_path)
    source.execute(
        "create table verses (book text, chapter integer, verse integer, text text, translation text)"
    )
    source.executemany(
        "insert into verses values (?, ?, ?, ?, ?)",
        [
            ("Genesis", 1, 1, "태초에 하나님이 천지를 창조하시니라", "KOR"),
            ("Genesis", 1, 2, "땅이 혼돈하고 공허하며", "KOR"),
            ("Genesis", 1, 3, "하나님이 이르시되 빛이 있으라 하시니", "KOR"),
        ],
    )
    source.commit()
    source.close()

    config = AppConfig(
        source=SourceBibleConfig(path=source_path, table="verses"),
        app_db_path=app_path,
        faiss_index_path=tmp_path / "index.faiss",
    )

    conn = connect_db(app_path)
    ensure_schema(conn)
    import_verses(config, conn)
    build_chunks(conn, max_verses=3, stride=2)
    rebuild_fts_indexes(conn)

    results = search_keyword(conn, "천지를")

    assert results[0]["reference"] == "Genesis 1:1"


def test_rebuild_and_reset_are_rerunnable_for_contentless_fts_tables(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.sqlite"
    app_path = tmp_path / "app.sqlite"

    source = sqlite3.connect(source_path)
    source.execute(
        "create table verses (book text, chapter integer, verse integer, text text, translation text)"
    )
    source.executemany(
        "insert into verses values (?, ?, ?, ?, ?)",
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

    conn = connect_db(app_path)
    ensure_schema(conn)
    import_verses(config, conn)
    build_chunks(conn, max_verses=3, stride=2)

    rebuild_fts_indexes(conn)
    rebuild_fts_indexes(conn)
    assert search_keyword(conn, "천지를")[0]["reference"] == "Genesis 1:1"

    reset_indexes(conn)
    reset_indexes(conn)

    assert conn.execute("select count(*) from verses_fts").fetchone()[0] == 0
    assert conn.execute("select count(*) from passage_chunks_fts").fetchone()[0] == 0


def test_reimport_clears_stale_keyword_matches_before_rebuild(tmp_path: Path) -> None:
    source1_path = tmp_path / "source1.sqlite"
    source2_path = tmp_path / "source2.sqlite"
    app_path = tmp_path / "app.sqlite"

    source1 = sqlite3.connect(source1_path)
    source1.execute(
        "create table verses (book text, chapter integer, verse integer, text text, translation text)"
    )
    source1.executemany(
        "insert into verses values (?, ?, ?, ?, ?)",
        [
            ("Genesis", 1, 1, "태초에 하나님이 천지를 창조하시니라", "KOR"),
            ("Genesis", 1, 2, "땅이 혼돈하고 공허하며", "KOR"),
        ],
    )
    source1.commit()
    source1.close()

    source2 = sqlite3.connect(source2_path)
    source2.execute(
        "create table verses (book text, chapter integer, verse integer, text text, translation text)"
    )
    source2.executemany(
        "insert into verses values (?, ?, ?, ?, ?)",
        [
            ("Genesis", 1, 1, "태초에 하늘과 땅을 창조하시니라", "KOR"),
            ("Genesis", 1, 2, "땅이 아직 모양을 갖추지 아니하였고", "KOR"),
        ],
    )
    source2.commit()
    source2.close()

    config1 = AppConfig(
        source=SourceBibleConfig(path=source1_path, table="verses"),
        app_db_path=app_path,
        faiss_index_path=tmp_path / "index.faiss",
    )
    config2 = AppConfig(
        source=SourceBibleConfig(path=source2_path, table="verses"),
        app_db_path=app_path,
        faiss_index_path=tmp_path / "index.faiss",
    )

    conn = connect_db(app_path)
    ensure_schema(conn)

    import_verses(config1, conn)
    build_chunks(conn, max_verses=3, stride=2)
    rebuild_fts_indexes(conn)
    assert search_keyword(conn, "천지를")[0]["reference"] == "Genesis 1:1"

    import_verses(config2, conn)
    build_chunks(conn, max_verses=3, stride=2)

    assert search_keyword(conn, "천지를") == []

    rebuild_fts_indexes(conn)
    assert search_keyword(conn, "천지를") == []
    assert search_keyword(conn, "하늘과")[0]["reference"] == "Genesis 1:1"


def test_search_keyword_treats_punctuation_as_plain_text(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    app_path = tmp_path / "app.sqlite"

    source = sqlite3.connect(source_path)
    source.execute(
        "create table verses (book text, chapter integer, verse integer, text text, translation text)"
    )
    source.executemany(
        "insert into verses values (?, ?, ?, ?, ?)",
        [("Genesis", 1, 1, "태초에 하나님이 천지를 창조하시니라", "KOR")],
    )
    source.commit()
    source.close()

    config = AppConfig(
        source=SourceBibleConfig(path=source_path, table="verses"),
        app_db_path=app_path,
        faiss_index_path=tmp_path / "index.faiss",
    )

    conn = connect_db(app_path)
    ensure_schema(conn)
    import_verses(config, conn)
    build_chunks(conn, max_verses=3, stride=2)
    rebuild_fts_indexes(conn)

    results = search_keyword(conn, "Genesis:1")

    assert results[0]["reference"] == "Genesis 1:1"
