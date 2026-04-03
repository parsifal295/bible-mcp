import re
from dataclasses import dataclass

from bible_mcp.query.book_aliases import BOOK_ALIASES


@dataclass
class ParsedReference:
    book: str
    chapter: int
    start_verse: int | None
    end_verse: int | None


REFERENCE_RE = re.compile(r"^\s*(.+?)\s+(\d+):(\d+)(?:-(\d+))?\s*$")
CHAPTER_RE = re.compile(r"^\s*(.+?)\s+(\d+)장\s*$")


def _normalize_book(raw_book: str) -> str | None:
    return BOOK_ALIASES.get(raw_book.strip().lower())


def parse_reference(text: str) -> ParsedReference | None:
    match = REFERENCE_RE.match(text)
    if match:
        raw_book, chapter, start_verse, end_verse = match.groups()
        normalized_book = _normalize_book(raw_book)
        if not normalized_book:
            return None
        return ParsedReference(
            book=normalized_book,
            chapter=int(chapter),
            start_verse=int(start_verse),
            end_verse=int(end_verse or start_verse),
        )

    chapter_match = CHAPTER_RE.match(text)
    if not chapter_match:
        return None

    raw_book, chapter = chapter_match.groups()
    normalized_book = _normalize_book(raw_book)
    if not normalized_book:
        return None
    return ParsedReference(
        book=normalized_book,
        chapter=int(chapter),
        start_verse=None,
        end_verse=None,
    )
