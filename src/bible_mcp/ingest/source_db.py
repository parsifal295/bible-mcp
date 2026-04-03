import sqlite3
from pathlib import Path

from bible_mcp.config import SourceBibleConfig


class SourceSchemaError(RuntimeError):
    pass


REQUIRED_COLUMNS = {"book", "chapter", "verse", "text"}


def _table_columns(db_path: Path, table: str) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(f"pragma table_info({table})").fetchall()
    finally:
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
