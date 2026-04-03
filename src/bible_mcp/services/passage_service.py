from dataclasses import dataclass

from bible_mcp.query.parser import parse_reference


@dataclass
class PassageResult:
    reference: str
    passage_text: str


class PassageService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def _reference_for_rows(self, rows) -> str:
        first = rows[0]
        last = rows[-1]
        if first["verse"] == last["verse"]:
            return f'{first["book"]} {first["chapter"]}:{first["verse"]}'
        return f'{first["book"]} {first["chapter"]}:{first["verse"]}-{last["verse"]}'

    def lookup(self, reference: str) -> PassageResult:
        parsed = parse_reference(reference)
        if parsed is None:
            raise ValueError(f"Invalid reference: {reference}")

        if parsed.start_verse is None:
            rows = self.conn.execute(
                """
                select book, chapter, verse, text
                from verses
                where book = ? and chapter = ?
                order by verse
                """,
                (parsed.book, parsed.chapter),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                select book, chapter, verse, text
                from verses
                where book = ? and chapter = ? and verse between ? and ?
                order by verse
                """,
                (parsed.book, parsed.chapter, parsed.start_verse, parsed.end_verse),
            ).fetchall()

        if not rows:
            raise LookupError(f"Passage not found: {reference}")

        return PassageResult(
            reference=self._reference_for_rows(rows),
            passage_text=" ".join(row["text"] for row in rows),
        )

    def expand_context(self, reference: str, window: int = 2) -> PassageResult:
        parsed = parse_reference(reference)
        if parsed is None or parsed.start_verse is None:
            raise ValueError(f"Context expansion requires a verse reference: {reference}")

        start_verse = max(1, parsed.start_verse - window)
        end_verse = parsed.end_verse + window
        rows = self.conn.execute(
            """
            select book, chapter, verse, text
            from verses
            where book = ? and chapter = ? and verse between ? and ?
            order by verse
            """,
            (parsed.book, parsed.chapter, start_verse, end_verse),
        ).fetchall()

        if not rows:
            raise LookupError(f"Passage not found: {reference}")

        return PassageResult(
            reference=self._reference_for_rows(rows),
            passage_text=" ".join(row["text"] for row in rows),
        )
