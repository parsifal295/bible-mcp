import json
import sqlite3
from pathlib import Path

import pytest

from bible_mcp.db.connection import connect_db
from bible_mcp.db.schema import ensure_schema
from bible_mcp.ingest.metadata_importer import import_metadata_fixtures


def _write_fixture(path: Path, name: str, payload) -> None:
    (path / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_minimal_metadata_bundle(
    fixtures: Path,
    *,
    alias_slug: str = "abraham",
    relationship_target: str = "isaac",
    relation_type: str = "father",
) -> None:
    _write_fixture(
        fixtures,
        "people.json",
        [
            {"slug": "abraham", "display_name": "아브라함", "description": "족장"},
            {"slug": "isaac", "display_name": "이삭", "description": "아브라함의 아들"},
        ],
    )
    _write_fixture(
        fixtures,
        "places.json",
        [
            {
                "slug": "jerusalem",
                "display_name": "예루살렘",
                "latitude": 31.778,
                "longitude": 35.235,
            }
        ],
    )
    _write_fixture(
        fixtures,
        "events.json",
        [
            {
                "slug": "crucifixion",
                "display_name": "십자가 처형",
                "description": "예수의 십자가 사건",
            }
        ],
    )
    _write_fixture(
        fixtures,
        "aliases.json",
        [{"entity_type": "people", "entity_slug": alias_slug, "alias": "Abram"}],
    )
    _write_fixture(
        fixtures,
        "entity_verse_links.json",
        [{"entity_type": "people", "entity_slug": "abraham", "reference": "Genesis 12:1"}],
    )
    _write_fixture(
        fixtures,
        "relationships.json",
        [
            {
                "source_type": "people",
                "source_slug": "abraham",
                "relation_type": relation_type,
                "target_type": "people",
                "target_slug": relationship_target,
                "is_primary": True,
                "note": "patriarch line",
            }
        ],
    )


def test_import_metadata_fixtures_populates_people_aliases_and_relationships(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    _write_minimal_metadata_bundle(fixtures)

    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)

    import_metadata_fixtures(conn, fixtures_dir=fixtures)

    people = conn.execute(
        "select slug, display_name, description from people order by slug"
    ).fetchall()
    aliases = conn.execute(
        "select entity_type, entity_slug, alias from entity_aliases order by entity_type, entity_slug, alias"
    ).fetchall()
    relationships = conn.execute(
        """
        select source_type, source_slug, relation_type, target_type, target_slug, is_primary, note
        from entity_relationships
        order by source_type, source_slug, relation_type, target_slug
        """
    ).fetchall()

    assert [tuple(row) for row in people] == [
        ("abraham", "아브라함", "족장"),
        ("isaac", "이삭", "아브라함의 아들"),
    ]
    assert [tuple(row) for row in aliases] == [
        ("people", "abraham", "Abram"),
    ]
    assert [tuple(row) for row in relationships] == [
        ("people", "abraham", "father", "people", "isaac", 1, "patriarch line"),
    ]


def test_import_metadata_fixtures_replaces_existing_rows_on_rebuild(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    _write_minimal_metadata_bundle(fixtures)

    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)

    import_metadata_fixtures(conn, fixtures_dir=fixtures)
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("stale", "오래된 이름", "stale"),
    )
    conn.execute(
        "insert into entity_aliases(entity_type, entity_slug, alias) values (?, ?, ?)",
        ("people", "stale", "Old Alias"),
    )
    conn.execute(
        """
        insert into entity_relationships(
            source_type, source_slug, relation_type, target_type, target_slug, is_primary, note
        )
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        ("people", "stale", "father", "people", "isaac", 0, None),
    )
    conn.commit()

    import_metadata_fixtures(conn, fixtures_dir=fixtures)

    people_slugs = [row[0] for row in conn.execute("select slug from people order by slug").fetchall()]
    alias_rows = conn.execute(
        "select entity_slug, alias from entity_aliases order by entity_slug, alias"
    ).fetchall()
    relationship_rows = conn.execute(
        "select source_slug, target_slug from entity_relationships order by source_slug, target_slug"
    ).fetchall()

    assert people_slugs == ["abraham", "isaac"]
    assert [tuple(row) for row in alias_rows] == [("abraham", "Abram")]
    assert [tuple(row) for row in relationship_rows] == [("abraham", "isaac")]


def test_import_metadata_fixtures_participates_in_caller_owned_transaction(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    _write_minimal_metadata_bundle(fixtures)

    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)
    conn.execute("create table audit_log(message text not null)")
    conn.commit()

    try:
        with conn:
            conn.execute(
                "insert into audit_log(message) values (?)",
                ("before import",),
            )
            import_metadata_fixtures(conn, fixtures_dir=fixtures)
            raise RuntimeError("abort outer transaction")
    except RuntimeError:
        pass

    assert conn.execute("select count(*) from audit_log").fetchone()[0] == 0
    assert conn.execute("select count(*) from people").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("fixture_name", "duplicate_payload", "count_query"),
    [
        (
            "aliases.json",
            [
                {"entity_type": "people", "entity_slug": "abraham", "alias": "Abram"},
                {"entity_type": "people", "entity_slug": "abraham", "alias": "Abram"},
            ],
            "select count(*) from entity_aliases",
        ),
        (
            "entity_verse_links.json",
            [
                {
                    "entity_type": "people",
                    "entity_slug": "abraham",
                    "reference": "Genesis 12:1",
                },
                {
                    "entity_type": "people",
                    "entity_slug": "abraham",
                    "reference": "Genesis 12:1",
                },
            ],
            "select count(*) from entity_verse_links",
        ),
        (
            "relationships.json",
            [
                {
                    "source_type": "people",
                    "source_slug": "abraham",
                    "relation_type": "father",
                    "target_type": "people",
                    "target_slug": "isaac",
                    "is_primary": True,
                    "note": "patriarch line",
                },
                {
                    "source_type": "people",
                    "source_slug": "abraham",
                    "relation_type": "father",
                    "target_type": "people",
                    "target_slug": "isaac",
                    "is_primary": True,
                    "note": "patriarch line",
                },
            ],
            "select count(*) from entity_relationships",
        ),
    ],
)
def test_import_metadata_fixtures_rejects_duplicate_metadata_rows(
    tmp_path: Path,
    fixture_name: str,
    duplicate_payload,
    count_query: str,
) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    _write_minimal_metadata_bundle(fixtures)
    _write_fixture(fixtures, fixture_name, duplicate_payload)

    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)

    with pytest.raises(sqlite3.IntegrityError):
        import_metadata_fixtures(conn, fixtures_dir=fixtures)

    conn.rollback()

    assert conn.execute(count_query).fetchone()[0] == 0


def test_import_metadata_fixtures_rejects_missing_alias_entity(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    _write_minimal_metadata_bundle(fixtures, alias_slug="missing")

    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)

    with pytest.raises(ValueError, match="missing.*alias"):
        import_metadata_fixtures(conn, fixtures_dir=fixtures)


def test_import_metadata_fixtures_rejects_unknown_relation_type(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    _write_minimal_metadata_bundle(fixtures, relation_type="grandfather")

    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)

    with pytest.raises(ValueError, match="grandfather"):
        import_metadata_fixtures(conn, fixtures_dir=fixtures)


def test_import_metadata_fixtures_rejects_missing_relationship_endpoint(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    _write_minimal_metadata_bundle(fixtures, relationship_target="missing")

    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)

    with pytest.raises(ValueError, match="missing.*relationship"):
        import_metadata_fixtures(conn, fixtures_dir=fixtures)
