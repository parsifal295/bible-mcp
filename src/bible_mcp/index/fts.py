import sqlite3


def rebuild_fts_indexes(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("delete from verses_fts")
        conn.execute("delete from passage_chunks_fts")
        conn.execute("insert into verses_fts(rowid, reference, text) select id, reference, text from verses")
        conn.execute(
            "insert into passage_chunks_fts(rowid, chunk_id, text) select id, chunk_id, text from passage_chunks"
        )


def search_keyword(conn: sqlite3.Connection, query: str, limit: int = 10):
    return conn.execute(
        """
        select v.reference, v.text
        from verses_fts
        join verses v on v.id = verses_fts.rowid
        where verses_fts match ?
        limit ?
        """,
        (query, limit),
    ).fetchall()
