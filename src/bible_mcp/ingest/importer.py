import sqlite3

from bible_mcp.config import AppConfig
from bible_mcp.domain.models import VerseRecord


BOOK_ORDER = {
    "Genesis": 1,
    "Exodus": 2,
    "Leviticus": 3,
    "Numbers": 4,
    "Deuteronomy": 5,
    "Joshua": 6,
    "Judges": 7,
    "Ruth": 8,
    "1 Samuel": 9,
    "2 Samuel": 10,
    "1 Kings": 11,
    "2 Kings": 12,
    "1 Chronicles": 13,
    "2 Chronicles": 14,
    "Ezra": 15,
    "Nehemiah": 16,
    "Esther": 17,
    "Job": 18,
    "Psalms": 19,
    "Proverbs": 20,
    "Ecclesiastes": 21,
    "Song of Solomon": 22,
    "Isaiah": 23,
    "Jeremiah": 24,
    "Lamentations": 25,
    "Ezekiel": 26,
    "Daniel": 27,
    "Hosea": 28,
    "Joel": 29,
    "Amos": 30,
    "Obadiah": 31,
    "Jonah": 32,
    "Micah": 33,
    "Nahum": 34,
    "Habakkuk": 35,
    "Zephaniah": 36,
    "Haggai": 37,
    "Zechariah": 38,
    "Malachi": 39,
    "Matthew": 40,
    "Mark": 41,
    "Luke": 42,
    "John": 43,
    "Acts": 44,
    "Romans": 45,
    "1 Corinthians": 46,
    "2 Corinthians": 47,
    "Galatians": 48,
    "Ephesians": 49,
    "Philippians": 50,
    "Colossians": 51,
    "1 Thessalonians": 52,
    "2 Thessalonians": 53,
    "1 Timothy": 54,
    "2 Timothy": 55,
    "Titus": 56,
    "Philemon": 57,
    "Hebrews": 58,
    "James": 59,
    "1 Peter": 60,
    "2 Peter": 61,
    "1 John": 62,
    "2 John": 63,
    "3 John": 64,
    "Jude": 65,
    "Revelation": 66,
}


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def import_verses(config: AppConfig, conn: sqlite3.Connection) -> None:
    source = sqlite3.connect(config.source.path)
    source.row_factory = sqlite3.Row
    try:
        rows = source.execute(
            f"""
            select book, chapter, verse, text, translation
            from {_quote_identifier(config.source.table)}
            order by book, chapter, verse
            """
        ).fetchall()
    finally:
        source.close()

    conn.execute("delete from verses")

    for row in rows:
        book = row["book"]
        chapter = int(row["chapter"])
        verse = int(row["verse"])
        book_order = BOOK_ORDER.get(book, 999)
        record = VerseRecord(
            book=book,
            chapter=chapter,
            verse=verse,
            reference=f"{book} {chapter}:{verse}",
            translation=row["translation"],
            testament="OT" if book_order <= 39 else "NT",
            book_order=book_order,
            text=row["text"],
        )
        conn.execute(
            """
            insert into verses(translation, book, book_order, chapter, verse, reference, testament, text)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.translation,
                record.book,
                record.book_order,
                record.chapter,
                record.verse,
                record.reference,
                record.testament,
                record.text,
            ),
        )
    conn.commit()
