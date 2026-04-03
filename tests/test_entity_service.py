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


def _create_partial_entity_schema_with_aliases(conn) -> None:
    conn.executescript(
        """
        create table people (
            id integer primary key,
            slug text not null unique,
            display_name text not null,
            description text
        );

        create table entity_aliases (
            id integer primary key,
            entity_type text not null,
            entity_slug text not null,
            alias text not null
        );
        """
    )
    conn.commit()


def _create_partial_entity_schema_without_aliases(conn) -> None:
    conn.executescript(
        """
        create table people (
            id integer primary key,
            slug text not null unique,
            display_name text not null,
            description text
        );
        """
    )
    conn.commit()


def _seed_default_bundle_verses(conn) -> None:
    conn.executemany(
        """
        insert into verses(translation, book, book_order, chapter, verse, reference, testament, text)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("KRV", "Genesis", 1, 12, 1, "Genesis 12:1", "OT", "Now the LORD had said unto Abram."),
            ("KRV", "Genesis", 1, 21, 3, "Genesis 21:3", "OT", "And Abraham called his son's name that was born unto him, whom Sarah bare to him, Isaac."),
            ("KRV", "Genesis", 1, 25, 26, "Genesis 25:26", "OT", "And after that came his brother out, and his hand took hold on Esau's heel; and his name was called Jacob."),
            ("KRV", "1 Samuel", 9, 16, 1, "1 Samuel 16:1", "OT", "And the LORD said unto Samuel, How long wilt thou mourn for Saul, seeing I have rejected him?"),
            ("KRV", "1 Samuel", 9, 16, 13, "1 Samuel 16:13", "OT", "Then Samuel took the horn of oil, and anointed him in the midst of his brethren."),
            ("KRV", "Matthew", 40, 1, 21, "Matthew 1:21", "NT", "And she shall bring forth a son, and thou shalt call his name JESUS."),
            ("KRV", "Matthew", 40, 4, 18, "Matthew 4:18", "NT", "Jesus, walking by the sea of Galilee, saw two brethren, Simon called Peter."),
            ("KRV", "Matthew", 40, 4, 21, "Matthew 4:21", "NT", "And going on from thence, he saw other two brethren, James the son of Zebedee, and John his brother."),
            ("KRV", "Psalms", 19, 122, 2, "Psalms 122:2", "OT", "Our feet shall stand within thy gates, O Jerusalem."),
            ("KRV", "Micah", 33, 5, 2, "Micah 5:2", "OT", "But thou, Bethlehem Ephratah, though thou be little among the thousands of Judah."),
            ("KRV", "Matthew", 40, 2, 23, "Matthew 2:23", "NT", "And he came and dwelt in a city called Nazareth."),
            ("KRV", "Matthew", 40, 4, 15, "Matthew 4:15", "NT", "The land of Zebulun, and the land of Naphtali, by the way of the sea, beyond Jordan, Galilee of the Gentiles."),
            ("KRV", "Matthew", 40, 3, 13, "Matthew 3:13", "NT", "Then cometh Jesus from Galilee to Jordan unto John, to be baptized of him."),
            ("KRV", "Exodus", 2, 12, 41, "Exodus 12:41", "OT", "And it came to pass at the end of the four hundred and thirty years."),
            ("KRV", "Matthew", 40, 27, 35, "Matthew 27:35", "NT", "And they crucified him, and parted his garments."),
            ("KRV", "Matthew", 40, 28, 6, "Matthew 28:6", "NT", "He is not here: for he is risen, as he said."),
        ],
    )
    conn.commit()


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
    _seed_default_bundle_verses(conn)
    import_metadata_fixtures(conn)

    assert service.search("Jerusalem", entity_type="angels", limit=5) == []


def test_search_handles_partial_schema_without_places_or_events_tables(tmp_path) -> None:
    conn = connect_db(tmp_path / "app.sqlite")
    _create_partial_entity_schema_with_aliases(conn)
    service = EntityService(conn)
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("saul", "Saul", "display match"),
    )
    conn.commit()

    assert service.search("Saul", limit=5) == [
        {
            "entity_type": "people",
            "slug": "saul",
            "display_name": "Saul",
            "description": "display match",
            "matched_by": "display_name",
        }
    ]
    assert service.search("Jerusalem", entity_type="places", limit=5) == []
    assert service.search("Resurrection", entity_type="events", limit=5) == []


def test_search_skips_alias_matching_when_entity_aliases_table_is_missing(tmp_path) -> None:
    conn = connect_db(tmp_path / "app.sqlite")
    _create_partial_entity_schema_without_aliases(conn)
    service = EntityService(conn)
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("abraham", "Abraham", "patriarch"),
    )
    conn.commit()

    assert service.search("Abraham", limit=5) == [
        {
            "entity_type": "people",
            "slug": "abraham",
            "display_name": "Abraham",
            "description": "patriarch",
            "matched_by": "display_name",
        }
    ]
    assert service.search("Father of many", limit=5) == []


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
    _seed_default_bundle_verses(conn)
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
    _seed_default_bundle_verses(conn)
    import_metadata_fixtures(conn)

    assert service.search("Jerusalem", limit=5) == []


def test_search_resolves_bundled_place_and_event_aliases(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    _seed_default_bundle_verses(conn)
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
