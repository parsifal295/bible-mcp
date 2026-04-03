from __future__ import annotations

import sqlite3

from bible_mcp.query.parser import parse_reference


def expand_chunk_context(
    conn: sqlite3.Connection,
    start_ref: str,
    end_ref: str,
    window: int = 1,
):
    start = parse_reference(start_ref)
    end = parse_reference(end_ref)
    if (
        start is None
        or end is None
        or start.start_verse is None
        or end.end_verse is None
        or start.book != end.book
    ):
        raise ValueError(f"Context expansion requires a verse range: {start_ref} - {end_ref}")

    rows = conn.execute(
        """
        select reference, text, chapter, verse
        from verses
        where book = ?
        order by chapter, verse
        """,
        (start.book,),
    ).fetchall()

    if not rows:
        return rows

    start_key = (start.chapter, start.start_verse)
    end_key = (end.chapter, end.end_verse)

    start_index = next(
        (index for index, row in enumerate(rows) if (row["chapter"], row["verse"]) >= start_key),
        None,
    )
    end_index = next(
        (
            index
            for index in range(len(rows) - 1, -1, -1)
            if (rows[index]["chapter"], rows[index]["verse"]) <= end_key
        ),
        None,
    )

    if start_index is None or end_index is None or start_index > end_index:
        return []

    start_index = max(0, start_index - window)
    end_index = min(len(rows) - 1, end_index + window)
    return rows[start_index : end_index + 1]
