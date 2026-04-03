from dataclasses import dataclass
from itertools import groupby
import sqlite3


@dataclass
class PassageChunk:
    chunk_id: str
    start_ref: str
    end_ref: str
    book: str
    chapter_range: str
    text: str
    token_count: int
    chunk_strategy: str


def _chapter_range(start_chapter: int, end_chapter: int) -> str:
    if start_chapter == end_chapter:
        return str(start_chapter)
    return f"{start_chapter}-{end_chapter}"


def build_chunks(
    conn: sqlite3.Connection,
    max_verses: int = 5,
    stride: int = 3,
) -> list[PassageChunk]:
    rows = conn.execute(
        """
        select reference, book, chapter, verse, text
        from verses
        order by book_order, chapter, verse
        """
    ).fetchall()

    chunks: list[PassageChunk] = []

    with conn:
        conn.execute("delete from passage_chunks")

        for _, book_rows_iter in groupby(rows, key=lambda row: row["book"]):
            book_rows = list(book_rows_iter)

            for start in range(0, len(book_rows), stride):
                window = book_rows[start : start + max_verses]
                if not window:
                    continue

                first = window[0]
                last = window[-1]
                chunk = PassageChunk(
                    chunk_id=f"{first['reference']}-{last['reference']}",
                    start_ref=first["reference"],
                    end_ref=last["reference"],
                    book=first["book"],
                    chapter_range=_chapter_range(
                        int(first["chapter"]), int(last["chapter"])
                    ),
                    text=" ".join(row["text"] for row in window),
                    token_count=sum(len(row["text"].split()) for row in window),
                    chunk_strategy="verse_window",
                )
                conn.execute(
                    """
                    insert into passage_chunks(
                        chunk_id,
                        start_ref,
                        end_ref,
                        book,
                        chapter_range,
                        text,
                        token_count,
                        chunk_strategy
                    )
                    values (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_id,
                        chunk.start_ref,
                        chunk.end_ref,
                        chunk.book,
                        chunk.chapter_range,
                        chunk.text,
                        chunk.token_count,
                        chunk.chunk_strategy,
                    ),
                )
                chunks.append(chunk)

    return chunks
