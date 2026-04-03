import sqlite3
from pathlib import Path

from bible_mcp.config import SourceBibleConfig


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
