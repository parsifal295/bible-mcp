from __future__ import annotations

import pytest

from bible_mcp.db.connection import connect_db
from bible_mcp.db.schema import ensure_schema
from bible_mcp.services.entity_service import EntityService
from bible_mcp.services.relation_service import RelationLookupService


def _build_service(tmp_path):
    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)
    return conn, RelationLookupService(conn, EntityService(conn))


def test_lookup_returns_empty_result_when_no_entity_matches(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    conn.commit()

    result = service.lookup("missing")

    assert result == {"resolved_entity": None, "matches": [], "relations": []}


def test_lookup_returns_candidates_without_relations_when_query_is_ambiguous(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("saul-a", "Saul", "first candidate"),
    )
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("saul-b", "Saul", "second candidate"),
    )
    conn.commit()

    result = service.lookup("Saul")

    assert result == {
        "resolved_entity": None,
        "matches": [
            {
                "entity_type": "people",
                "slug": "saul-a",
                "display_name": "Saul",
                "description": "first candidate",
                "matched_by": "display_name",
            },
            {
                "entity_type": "people",
                "slug": "saul-b",
                "display_name": "Saul",
                "description": "second candidate",
                "matched_by": "display_name",
            },
        ],
        "relations": [],
    }


def test_lookup_returns_outgoing_relations_for_a_unique_entity(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("abraham", "Abraham", "patriarch"),
    )
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("isaac", "Isaac", "son 1"),
    )
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("ishmael", "Ishmael", "son 2"),
    )
    conn.execute(
        """
        insert into entity_relationships(
            source_type,
            source_slug,
            relation_type,
            target_type,
            target_slug,
            is_primary,
            note
        ) values (?, ?, ?, ?, ?, ?, ?)
        """,
        ("people", "abraham", "father", "people", "isaac", 1, "patriarch line"),
    )
    conn.execute(
        """
        insert into entity_relationships(
            source_type,
            source_slug,
            relation_type,
            target_type,
            target_slug,
            is_primary,
            note
        ) values (?, ?, ?, ?, ?, ?, ?)
        """,
        ("people", "abraham", "father", "people", "ishmael", 1, "patriarch line"),
    )
    conn.commit()

    result = service.lookup("Abraham", relation_type="father", limit=1)

    assert result == {
        "resolved_entity": {
            "entity_type": "people",
            "slug": "abraham",
            "display_name": "Abraham",
            "description": "patriarch",
            "matched_by": "display_name",
        },
        "matches": [],
        "relations": [
            {
                "relation_type": "father",
                "entity_type": "people",
                "slug": "isaac",
                "display_name": "Isaac",
                "description": "son 1",
            }
        ],
    }


def test_lookup_deduplicates_visible_relation_rows(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("abraham", "Abraham", "patriarch"),
    )
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("isaac", "Isaac", "son"),
    )
    conn.execute(
        """
        insert into entity_relationships(
            source_type,
            source_slug,
            relation_type,
            target_type,
            target_slug,
            is_primary,
            note
        ) values (?, ?, ?, ?, ?, ?, ?)
        """,
        ("people", "abraham", "father", "people", "isaac", 1, "patriarch line"),
    )
    conn.execute(
        """
        insert into entity_relationships(
            source_type,
            source_slug,
            relation_type,
            target_type,
            target_slug,
            is_primary,
            note
        ) values (?, ?, ?, ?, ?, ?, ?)
        """,
        ("people", "abraham", "father", "people", "isaac", 0, "alternate note"),
    )
    conn.commit()

    result = service.lookup("Abraham", relation_type="father")

    assert result == {
        "resolved_entity": {
            "entity_type": "people",
            "slug": "abraham",
            "display_name": "Abraham",
            "description": "patriarch",
            "matched_by": "display_name",
        },
        "matches": [],
        "relations": [
            {
                "relation_type": "father",
                "entity_type": "people",
                "slug": "isaac",
                "display_name": "Isaac",
                "description": "son",
            }
        ],
    }


def test_lookup_returns_incoming_relations_for_a_unique_entity(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("abraham", "Abraham", "patriarch"),
    )
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("isaac", "Isaac", "son"),
    )
    conn.execute(
        """
        insert into entity_relationships(
            source_type,
            source_slug,
            relation_type,
            target_type,
            target_slug,
            is_primary,
            note
        ) values (?, ?, ?, ?, ?, ?, ?)
        """,
        ("people", "abraham", "father", "people", "isaac", 1, "patriarch line"),
    )
    conn.commit()

    result = service.lookup("Isaac", direction="incoming")

    assert result == {
        "resolved_entity": {
            "entity_type": "people",
            "slug": "isaac",
            "display_name": "Isaac",
            "description": "son",
            "matched_by": "display_name",
        },
        "matches": [],
        "relations": [
            {
                "relation_type": "father",
                "entity_type": "people",
                "slug": "abraham",
                "display_name": "Abraham",
                "description": "patriarch",
            }
        ],
    }


def test_lookup_rejects_unknown_direction(tmp_path) -> None:
    _, service = _build_service(tmp_path)

    with pytest.raises(ValueError, match="direction must be 'incoming' or 'outgoing'"):
        service.lookup("Abraham", direction="sideways")


def test_lookup_rejects_non_people_entity_types_explicitly(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("abraham", "Abraham", "patriarch"),
    )
    conn.commit()

    result = service.lookup("Abraham", entity_type="events")

    assert result == {"resolved_entity": None, "matches": [], "relations": []}
