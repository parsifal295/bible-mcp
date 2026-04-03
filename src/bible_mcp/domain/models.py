from pydantic import BaseModel


class VerseRecord(BaseModel):
    book: str
    chapter: int
    verse: int
    reference: str
    translation: str | None = None
    testament: str | None = None
    book_order: int
    text: str
