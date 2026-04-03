import sqlite3

import pytest

from bible_mcp.config import SourceBibleConfig
from bible_mcp.ingest.source_db import SourceSchemaError, validate_source_database


def test_validate_source_database_accepts_required_columns(temp_dir) -> None:
    source_path = temp_dir / "source.sqlite"
    conn = sqlite3.connect(source_path)
    conn.execute(
        """
        create table verses (
            book text not null,
            chapter integer not null,
            verse integer not null,
            text text not null,
            translation text
        )
        """
    )
    conn.commit()
    conn.close()

    columns = validate_source_database(SourceBibleConfig(path=source_path, table="verses"))

    assert set(columns) >= {"book", "chapter", "verse", "text"}


def test_validate_source_database_rejects_missing_text_column(temp_dir) -> None:
    source_path = temp_dir / "broken.sqlite"
    conn = sqlite3.connect(source_path)
    conn.execute(
        """
        create table verses (
            book text not null,
            chapter integer not null,
            verse integer not null
        )
        """
    )
    conn.commit()
    conn.close()

    with pytest.raises(SourceSchemaError):
        validate_source_database(SourceBibleConfig(path=source_path, table="verses"))


def test_validate_source_database_reports_missing_table(temp_dir) -> None:
    source_path = temp_dir / "missing-table.sqlite"
    sqlite3.connect(source_path).close()

    with pytest.raises(SourceSchemaError, match="Source table not found"):
        validate_source_database(SourceBibleConfig(path=source_path, table="verses"))


def test_validate_source_database_accepts_quoted_table_name(temp_dir) -> None:
    source_path = temp_dir / "quoted.sqlite"
    conn = sqlite3.connect(source_path)
    conn.execute(
        """
        create table "verse entries" (
            book text not null,
            chapter integer not null,
            verse integer not null,
            text text not null
        )
        """
    )
    conn.commit()
    conn.close()

    columns = validate_source_database(
        SourceBibleConfig(path=source_path, table="verse entries")
    )

    assert set(columns) >= {"book", "chapter", "verse", "text"}


def test_validate_source_database_wraps_sqlite_errors(temp_dir) -> None:
    source_path = temp_dir / "not-a-db.sqlite"
    source_path.write_text("not sqlite")

    with pytest.raises(SourceSchemaError):
        validate_source_database(SourceBibleConfig(path=source_path, table="verses"))
