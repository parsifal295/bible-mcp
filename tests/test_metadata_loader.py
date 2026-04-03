import json
from pathlib import Path

import pytest

from bible_mcp.db.connection import connect_db
from bible_mcp.db.schema import ensure_schema
from bible_mcp.domain.metadata import ENTITY_TYPES, RELATION_DIRECTIONS, RELATION_TYPES
from bible_mcp.metadata.loader import DEFAULT_FIXTURE_DIR, load_metadata_fixtures


def _write_fixture(path: Path, name: str, payload) -> None:
    (path / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_ensure_schema_creates_entity_relationships_table(tmp_path: Path) -> None:
    conn = connect_db(tmp_path / "app.sqlite")

    ensure_schema(conn)

    row = conn.execute(
        "select name from sqlite_master where type = 'table' and name = 'entity_relationships'"
    ).fetchone()
    assert row[0] == "entity_relationships"

    source_idx = conn.execute(
        "select name from sqlite_master where type = 'index' and name = 'idx_entity_relationships_source'"
    ).fetchone()
    target_idx = conn.execute(
        "select name from sqlite_master where type = 'index' and name = 'idx_entity_relationships_target'"
    ).fetchone()
    alias_unique_idx = conn.execute(
        "select name from sqlite_master where type = 'index' and name = 'idx_entity_aliases_unique'"
    ).fetchone()
    verse_unique_idx = conn.execute(
        "select name from sqlite_master where type = 'index' and name = 'idx_entity_verse_links_unique'"
    ).fetchone()
    relationship_unique_idx = conn.execute(
        "select name from sqlite_master where type = 'index' and name = 'idx_entity_relationships_unique'"
    ).fetchone()
    assert source_idx[0] == "idx_entity_relationships_source"
    assert target_idx[0] == "idx_entity_relationships_target"
    assert alias_unique_idx[0] == "idx_entity_aliases_unique"
    assert verse_unique_idx[0] == "idx_entity_verse_links_unique"
    assert relationship_unique_idx[0] == "idx_entity_relationships_unique"


def test_metadata_constants_match_contract() -> None:
    assert ENTITY_TYPES == {"people", "places", "events"}
    assert RELATION_DIRECTIONS == ("incoming", "outgoing")
    assert RELATION_TYPES == {
        "father",
        "mother",
        "son",
        "daughter",
        "child",
        "spouse",
        "brother",
        "sister",
        "disciple_of",
    }


def test_load_metadata_fixtures_reads_fixture_bundle(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    _write_fixture(
        fixtures,
        "people.json",
        [{"slug": "jacob", "display_name": "야곱", "description": "이스라엘"}],
    )
    _write_fixture(
        fixtures,
        "places.json",
        [{"slug": "jerusalem", "display_name": "예루살렘", "latitude": 31.778, "longitude": 35.235}],
    )
    _write_fixture(fixtures, "events.json", [])
    _write_fixture(
        fixtures,
        "aliases.json",
        [{"entity_type": "people", "entity_slug": "jacob", "alias": "Jacob"}],
    )
    _write_fixture(
        fixtures,
        "entity_verse_links.json",
        [{"entity_type": "people", "entity_slug": "jacob", "reference": "Genesis 25:26"}],
    )
    _write_fixture(
        fixtures,
        "relationships.json",
        [{
            "source_type": "people",
            "source_slug": "jacob",
            "relation_type": "father",
            "target_type": "people",
            "target_slug": "isaac",
            "is_primary": True,
            "note": "patriarch line",
        }],
    )

    bundle = load_metadata_fixtures(fixtures)

    assert bundle.people[0].slug == "jacob"
    assert bundle.aliases[0].alias == "Jacob"
    assert bundle.relationships[0].relation_type == "father"


def test_load_metadata_fixtures_rejects_unknown_relation_type(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    _write_fixture(fixtures, "people.json", [{"slug": "jacob", "display_name": "야곱", "description": "이스라엘"}])
    _write_fixture(fixtures, "places.json", [])
    _write_fixture(fixtures, "events.json", [])
    _write_fixture(fixtures, "aliases.json", [])
    _write_fixture(fixtures, "entity_verse_links.json", [])
    _write_fixture(
        fixtures,
        "relationships.json",
        [{
            "source_type": "people",
            "source_slug": "jacob",
            "relation_type": "grandfather",
            "target_type": "people",
            "target_slug": "joseph",
            "is_primary": True,
            "note": "",
        }],
    )

    with pytest.raises(ValueError):
        load_metadata_fixtures(fixtures)


def test_load_metadata_fixtures_rejects_unknown_entity_type(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    _write_fixture(fixtures, "people.json", [{"slug": "jacob", "display_name": "야곱", "description": "이스라엘"}])
    _write_fixture(fixtures, "places.json", [])
    _write_fixture(fixtures, "events.json", [])
    _write_fixture(
        fixtures,
        "aliases.json",
        [{"entity_type": "angels", "entity_slug": "jacob", "alias": "Jacob"}],
    )
    _write_fixture(fixtures, "entity_verse_links.json", [])
    _write_fixture(fixtures, "relationships.json", [])

    with pytest.raises(ValueError):
        load_metadata_fixtures(fixtures)


def test_default_fixture_bundle_contains_representative_people_places_events_and_relationships() -> None:
    assert DEFAULT_FIXTURE_DIR == Path(__file__).resolve().parents[1] / "src" / "bible_mcp" / "metadata" / "fixtures"

    bundle = load_metadata_fixtures()
    people_slugs = {person.slug for person in bundle.people}
    place_slugs = {place.slug for place in bundle.places}
    event_slugs = {event.slug for event in bundle.events}
    assert {"abraham", "isaac", "jacob", "jesse", "david", "jesus", "peter", "john"} <= people_slugs
    assert {"jerusalem", "bethlehem", "nazareth", "galilee", "jordan-river"} <= place_slugs
    assert {"exodus", "crucifixion", "resurrection"} <= event_slugs
    assert {alias.entity_type for alias in bundle.aliases} == {"people", "places", "events"}
    assert {link.entity_type for link in bundle.entity_verse_links} == {"people"}
    aliases = {(alias.entity_type, alias.entity_slug, alias.alias) for alias in bundle.aliases}
    assert ("people", "abraham", "Abraham") in aliases
    assert ("people", "david", "David") in aliases
    assert ("people", "jesus", "Jesus") in aliases
    assert ("places", "jerusalem", "Jerusalem") in aliases
    assert ("places", "nazareth", "Nazareth") in aliases
    assert ("events", "resurrection", "Resurrection") in aliases
    assert ("events", "crucifixion", "십자가 사건") in aliases

    relation_pairs = {
        (row.source_slug, row.relation_type, row.target_slug)
        for row in bundle.relationships
    }
    assert ("abraham", "father", "isaac") in relation_pairs
    assert ("isaac", "father", "jacob") in relation_pairs
    assert ("jesse", "father", "david") in relation_pairs
    assert ("peter", "disciple_of", "jesus") in relation_pairs
