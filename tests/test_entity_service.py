from __future__ import annotations

from bible_mcp.db.connection import connect_db
from bible_mcp.db.schema import ensure_schema
from bible_mcp.services.entity_service import EntityService


def _build_service(tmp_path):
    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)
    return conn, EntityService(conn)


def test_search_orders_display_name_alias_and_slug_matches_deterministically(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("saul-display", "Saul", "display match"),
    )
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("aaron", "Aaron", "alias match 1"),
    )
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("barnabas", "Barnabas", "alias match 2"),
    )
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("Saul", "Not Saul", "slug match"),
    )
    conn.execute(
        "insert into entity_aliases(entity_type, entity_slug, alias) values (?, ?, ?)",
        ("people", "aaron", "Saul"),
    )
    conn.execute(
        "insert into entity_aliases(entity_type, entity_slug, alias) values (?, ?, ?)",
        ("people", "barnabas", "Saul"),
    )
    conn.commit()

    matches = service.search("Saul", limit=10)

    assert matches == [
        {
            "entity_type": "people",
            "slug": "saul-display",
            "display_name": "Saul",
            "description": "display match",
            "matched_by": "display_name",
        },
        {
            "entity_type": "people",
            "slug": "aaron",
            "display_name": "Aaron",
            "description": "alias match 1",
            "matched_by": "alias",
        },
        {
            "entity_type": "people",
            "slug": "barnabas",
            "display_name": "Barnabas",
            "description": "alias match 2",
            "matched_by": "alias",
        },
        {
            "entity_type": "people",
            "slug": "Saul",
            "display_name": "Not Saul",
            "description": "slug match",
            "matched_by": "slug",
        },
    ]


def test_search_respects_entity_type_filter_and_limit(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("saul-display", "Saul", "display match"),
    )
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("aaron", "Aaron", "alias match 1"),
    )
    conn.execute(
        "insert into entity_aliases(entity_type, entity_slug, alias) values (?, ?, ?)",
        ("people", "aaron", "Saul"),
    )
    conn.commit()

    assert service.search("Saul", entity_type="events", limit=10) == []
    assert service.search("Saul", entity_type="people", limit=1) == [
        {
            "entity_type": "people",
            "slug": "saul-display",
            "display_name": "Saul",
            "description": "display match",
            "matched_by": "display_name",
        }
    ]
