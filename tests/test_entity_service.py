from __future__ import annotations

import pytest

from bible_mcp.db.connection import connect_db
from bible_mcp.db.schema import ensure_schema
from bible_mcp.ingest.metadata_importer import import_metadata_fixtures
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


def test_search_returns_empty_list_for_unsupported_entity_types(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    import_metadata_fixtures(conn)

    assert service.search("Jerusalem", entity_type="angels", limit=5) == []


def test_search_keeps_highest_priority_match_for_same_entity(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("saul", "Saul", "same entity"),
    )
    conn.execute(
        "insert into entity_aliases(entity_type, entity_slug, alias) values (?, ?, ?)",
        ("people", "saul", "Saul"),
    )
    conn.commit()

    matches = service.search("Saul", limit=10)

    assert matches == [
        {
            "entity_type": "people",
            "slug": "saul",
            "display_name": "Saul",
            "description": "same entity",
            "matched_by": "display_name",
        }
    ]


def test_search_rejects_limit_below_one(tmp_path) -> None:
    conn, service = _build_service(tmp_path)

    with pytest.raises(ValueError, match="limit must be at least 1"):
        service.search("Saul", limit=0)


@pytest.mark.parametrize(
    ("query", "slug", "display_name", "description"),
    [
        ("Abraham", "abraham", "아브라함", "믿음의 조상으로 불린 족장"),
        ("David", "david", "다윗", "이스라엘 왕"),
        ("Jesus", "jesus", "예수", "신약의 중심 인물"),
    ],
)
def test_search_resolves_english_aliases_from_default_fixture_bundle(
    tmp_path,
    query: str,
    slug: str,
    display_name: str,
    description: str,
) -> None:
    conn, service = _build_service(tmp_path)
    import_metadata_fixtures(conn)

    assert service.search(query, entity_type="people", limit=1) == [
        {
            "entity_type": "people",
            "slug": slug,
            "display_name": display_name,
            "description": description,
            "matched_by": "alias",
        }
    ]


def test_search_keeps_default_scope_people_only_with_bundled_place_aliases(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    import_metadata_fixtures(conn)

    assert service.search("Jerusalem", limit=5) == []


def test_search_resolves_bundled_place_and_event_aliases(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    import_metadata_fixtures(conn)

    assert service.search("Jerusalem", entity_type="places", limit=5) == [
        {
            "entity_type": "places",
            "slug": "jerusalem",
            "display_name": "예루살렘",
            "description": None,
            "matched_by": "alias",
        }
    ]
    assert service.search("Resurrection", entity_type="events", limit=5) == [
        {
            "entity_type": "events",
            "slug": "resurrection",
            "display_name": "부활",
            "description": "예수의 부활 사건",
            "matched_by": "alias",
        }
    ]
