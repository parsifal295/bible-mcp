import sqlite3
from pathlib import Path

from bible_mcp.config import SourceBibleConfig
from bible_mcp.query.parser import parse_reference


class SourceSchemaError(RuntimeError):
    pass


REQUIRED_COLUMNS = {"book", "chapter", "verse", "text"}


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _table_columns(db_path: Path, table: str) -> list[str]:
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(f"pragma table_info({_quote_identifier(table)})").fetchall()
        if not rows:
            raise SourceSchemaError(f"Source table not found: {table} in {db_path}")
    except sqlite3.Error as exc:
        raise SourceSchemaError(f"Failed to inspect source database: {db_path}") from exc
    finally:
        if conn is not None:
            conn.close()
    return [row[1] for row in rows]


def validate_source_database(config: SourceBibleConfig) -> list[str]:
    if not config.path.exists():
        raise SourceSchemaError(f"Source DB not found: {config.path}")

    columns = _table_columns(config.path, config.table)
    missing = REQUIRED_COLUMNS.difference(columns)
    if missing:
        ordered = ", ".join(sorted(missing))
        raise SourceSchemaError(f"Missing required source columns: {ordered}")
    return columns


def validate_source_reference(config: SourceBibleConfig, reference: str) -> None:
    parsed = parse_reference(reference)
    if (
        parsed is None
        or parsed.start_verse is None
        or parsed.end_verse is None
        or parsed.start_verse != parsed.end_verse
    ):
        raise SourceSchemaError(f"Source reference must be a single verse: {reference}")

    validate_source_database(config)

    conn = None
    try:
        conn = sqlite3.connect(config.path)
        row = conn.execute(
            f"""
            select 1
            from {_quote_identifier(config.table)}
            where book = ? and chapter = ? and verse = ?
            limit 1
            """,
            (parsed.book, parsed.chapter, parsed.start_verse),
        ).fetchone()
    except sqlite3.Error as exc:
        raise SourceSchemaError(f"Failed to validate source reference: {reference}") from exc
    finally:
        if conn is not None:
            conn.close()

    if row is None:
        raise SourceSchemaError(f"Source reference not found: {reference}")
