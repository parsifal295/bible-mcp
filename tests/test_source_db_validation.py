import sqlite3
from pathlib import Path

import pytest

from bible_mcp.config import AppConfig, SourceBibleConfig
from bible_mcp.ingest.source_db import SourceSchemaError, validate_source_database


def test_validate_source_database_accepts_required_columns(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
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

    config = AppConfig(
        source=SourceBibleConfig(path=source_path, table="verses"),
        app_db_path=tmp_path / "app.sqlite",
        faiss_index_path=tmp_path / "index.faiss",
    )

    columns = validate_source_database(config.source)

    assert set(columns) >= {"book", "chapter", "verse", "text"}


def test_validate_source_database_rejects_missing_text_column(tmp_path: Path) -> None:
    source_path = tmp_path / "broken.sqlite"
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
