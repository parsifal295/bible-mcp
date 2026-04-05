from __future__ import annotations

import pytest

from bible_mcp.db.connection import connect_db
from bible_mcp.db.schema import ensure_schema
from bible_mcp.services.entity_passage_service import EntityPassageService
from bible_mcp.services.entity_service import EntityService
from bible_mcp.services.passage_service import PassageService


def _build_service(tmp_path):
    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)
    return conn, EntityPassageService(conn, EntityService(conn), PassageService(conn))


def _create_partial_entity_schema_with_links(conn) -> None:
    conn.executescript(
        """
        create table verses (
            id integer primary key,
            translation text,
            book text not null,
            book_order integer not null,
            chapter integer not null,
            verse integer not null,
            reference text not null unique,
            testament text,
            text text not null
        );

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

        create table entity_verse_links (
            id integer primary key,
            entity_type text not null,
            entity_slug text not null,
            reference text not null
        );
        """
    )
    conn.commit()


def _create_partial_entity_schema_without_links(conn) -> None:
    conn.executescript(
        """
        create table verses (
            id integer primary key,
            translation text,
            book text not null,
            book_order integer not null,
            chapter integer not null,
            verse integer not null,
            reference text not null unique,
            testament text,
            text text not null
        );

        create table people (
            id integer primary key,
            slug text not null unique,
            display_name text not null,
            description text
        );
        """
    )
    conn.commit()


def _seed_verses(conn) -> None:
    conn.executemany(
        """
        insert into verses(translation, book, book_order, chapter, verse, reference, testament, text)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("KRV", "Genesis", 1, 12, 1, "Genesis 12:1", "OT", "Now the LORD had said unto Abram."),
            ("KRV", "Genesis", 1, 21, 3, "Genesis 21:3", "OT", "And Abraham called his son's name that was born unto him, whom Sarah bare to him, Isaac."),
            ("KRV", "Psalms", 19, 122, 2, "Psalms 122:2", "OT", "Our feet shall stand within thy gates, O Jerusalem."),
            ("KRV", "Matthew", 40, 28, 6, "Matthew 28:6", "NT", "He is not here: for he is risen, as he said."),
        ],
    )


def test_lookup_returns_empty_result_when_no_entity_matches(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    conn.commit()

    result = service.lookup("missing")

    assert result == {"resolved_entity": None, "matches": [], "passages": []}


def test_lookup_returns_empty_result_for_missing_places_table_on_partial_schema(tmp_path) -> None:
    conn = connect_db(tmp_path / "app.sqlite")
    _create_partial_entity_schema_with_links(conn)
    service = EntityPassageService(conn, EntityService(conn), PassageService(conn))
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("abraham", "Abraham", "patriarch"),
    )
    conn.execute(
        "insert into entity_verse_links(entity_type, entity_slug, reference) values (?, ?, ?)",
        ("people", "abraham", "Genesis 12:1"),
    )
    conn.commit()

    assert service.lookup("Jerusalem", entity_type="places") == {
        "resolved_entity": None,
        "matches": [],
        "passages": [],
    }


def test_lookup_returns_empty_passages_when_entity_verse_links_table_is_missing(tmp_path) -> None:
    conn = connect_db(tmp_path / "app.sqlite")
    _create_partial_entity_schema_without_links(conn)
    service = EntityPassageService(conn, EntityService(conn), PassageService(conn))
    _seed_verses(conn)
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("abraham", "Abraham", "patriarch"),
    )
    conn.commit()

    assert service.lookup("Abraham", limit=1) == {
        "resolved_entity": {
            "entity_type": "people",
            "slug": "abraham",
            "display_name": "Abraham",
            "description": "patriarch",
            "matched_by": "display_name",
        },
        "matches": [],
        "passages": [],
    }


def test_lookup_returns_passages_for_people_on_partial_schema(tmp_path) -> None:
    conn = connect_db(tmp_path / "app.sqlite")
    _create_partial_entity_schema_with_links(conn)
    service = EntityPassageService(conn, EntityService(conn), PassageService(conn))
    _seed_verses(conn)
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("abraham", "Abraham", "patriarch"),
    )
    conn.execute(
        "insert into entity_verse_links(entity_type, entity_slug, reference) values (?, ?, ?)",
        ("people", "abraham", "Genesis 12:1"),
    )
    conn.commit()

    assert service.lookup("Abraham", limit=1) == {
        "resolved_entity": {
            "entity_type": "people",
            "slug": "abraham",
            "display_name": "Abraham",
            "description": "patriarch",
            "matched_by": "display_name",
        },
        "matches": [],
        "passages": [
            {
                "reference": "Genesis 12:1",
                "passage_text": "Now the LORD had said unto Abram.",
            }
        ],
    }


def test_lookup_returns_candidates_without_passages_when_query_is_ambiguous(tmp_path) -> None:
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
        "passages": [],
    }


def test_lookup_returns_passages_for_a_unique_people_entity(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    _seed_verses(conn)
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("abraham", "Abraham", "patriarch"),
    )
    conn.executemany(
        "insert into entity_verse_links(entity_type, entity_slug, reference) values (?, ?, ?)",
        [
            ("people", "abraham", "Genesis 12:1"),
            ("people", "abraham", "Genesis 21:3"),
        ],
    )
    conn.commit()

    result = service.lookup("Abraham", limit=1)

    assert result == {
        "resolved_entity": {
            "entity_type": "people",
            "slug": "abraham",
            "display_name": "Abraham",
            "description": "patriarch",
            "matched_by": "display_name",
        },
        "matches": [],
        "passages": [
            {
                "reference": "Genesis 12:1",
                "passage_text": "Now the LORD had said unto Abram.",
            }
        ],
    }


def test_lookup_returns_passages_for_a_unique_place_entity(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    _seed_verses(conn)
    conn.execute(
        "insert into places(slug, display_name, latitude, longitude) values (?, ?, ?, ?)",
        ("jerusalem", "Jerusalem", 31.7683, 35.2137),
    )
    conn.execute(
        "insert into entity_verse_links(entity_type, entity_slug, reference) values (?, ?, ?)",
        ("places", "jerusalem", "Psalms 122:2"),
    )
    conn.commit()

    result = service.lookup("Jerusalem", entity_type="places")

    assert result == {
        "resolved_entity": {
            "entity_type": "places",
            "slug": "jerusalem",
            "display_name": "Jerusalem",
            "description": None,
            "latitude": 31.7683,
            "longitude": 35.2137,
            "google_maps_url": "https://www.google.com/maps?q=31.7683,35.2137",
            "matched_by": "display_name",
        },
        "matches": [],
        "passages": [
            {
                "reference": "Psalms 122:2",
                "passage_text": "Our feet shall stand within thy gates, O Jerusalem.",
            }
        ],
    }


def test_lookup_returns_passages_for_a_unique_event_entity(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    _seed_verses(conn)
    conn.execute(
        "insert into events(slug, display_name, description) values (?, ?, ?)",
        ("resurrection", "Resurrection", "central event"),
    )
    conn.execute(
        "insert into entity_verse_links(entity_type, entity_slug, reference) values (?, ?, ?)",
        ("events", "resurrection", "Matthew 28:6"),
    )
    conn.commit()

    result = service.lookup("Resurrection", entity_type="events")

    assert result == {
        "resolved_entity": {
            "entity_type": "events",
            "slug": "resurrection",
            "display_name": "Resurrection",
            "description": "central event",
            "matched_by": "display_name",
        },
        "matches": [],
        "passages": [
            {
                "reference": "Matthew 28:6",
                "passage_text": "He is not here: for he is risen, as he said.",
            }
        ],
    }


def test_lookup_returns_empty_result_for_unsupported_entity_type(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    conn.execute(
        "insert into people(slug, display_name, description) values (?, ?, ?)",
        ("abraham", "Abraham", "patriarch"),
    )
    conn.commit()

    result = service.lookup("Abraham", entity_type="angels")

    assert result == {"resolved_entity": None, "matches": [], "passages": []}


def test_lookup_rejects_limit_below_one(tmp_path) -> None:
    _, service = _build_service(tmp_path)

    with pytest.raises(ValueError, match="limit must be at least 1"):
        service.lookup("Abraham", limit=0)
