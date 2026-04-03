import re
import sqlite3


def _clear_contentless_fts_table(conn: sqlite3.Connection, table_name: str) -> None:
    conn.execute(f"insert into {table_name}({table_name}) values('delete-all')")


def _normalize_keyword_query(query: str) -> str | None:
    tokens = re.findall(r"\w+", query, flags=re.UNICODE)
    if not tokens:
        return None
    return " ".join(f'"{token.replace("\"", "\"\"")}"' for token in tokens)


def rebuild_fts_indexes(conn: sqlite3.Connection) -> None:
    with conn:
        _clear_contentless_fts_table(conn, "verses_fts")
        _clear_contentless_fts_table(conn, "passage_chunks_fts")
        conn.execute("insert into verses_fts(rowid, reference, text) select id, reference, text from verses")
        conn.execute(
            "insert into passage_chunks_fts(rowid, chunk_id, text) select id, chunk_id, text from passage_chunks"
        )


def search_keyword(conn: sqlite3.Connection, query: str, limit: int = 10):
    safe_query = _normalize_keyword_query(query)
    if safe_query is None:
        return []

    return conn.execute(
        """
        select v.reference, v.text
        from verses_fts
        join verses v on v.id = verses_fts.rowid
        where verses_fts match ?
        limit ?
        """,
        (safe_query, limit),
    ).fetchall()
