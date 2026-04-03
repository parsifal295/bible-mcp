import json
from pathlib import Path

from .models import (
    ENTITY_TYPES,
    RELATION_TYPES,
    EntityAliasRecord,
    EntityRelationshipRecord,
    EntityVerseLinkRecord,
    MetadataBundle,
    MetadataEntity,
    PlaceRecord,
)


DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_fixture(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Fixture must contain a list: {path}")
    return payload


def _validate_entity_type(entity_type: str) -> None:
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"Unknown entity_type: {entity_type}")


def _validate_relation_type(relation_type: str) -> None:
    if relation_type not in RELATION_TYPES:
        raise ValueError(f"Unknown relation_type: {relation_type}")


def load_metadata_fixtures(fixtures_dir: Path = DEFAULT_FIXTURE_DIR) -> MetadataBundle:
    people = [
        MetadataEntity.model_validate(row)
        for row in _load_fixture(fixtures_dir / "people.json")
    ]
    places = [
        PlaceRecord.model_validate(row)
        for row in _load_fixture(fixtures_dir / "places.json")
    ]
    events = [
        MetadataEntity.model_validate(row)
        for row in _load_fixture(fixtures_dir / "events.json")
    ]

    aliases: list[EntityAliasRecord] = []
    for row in _load_fixture(fixtures_dir / "aliases.json"):
        record = EntityAliasRecord.model_validate(row)
        _validate_entity_type(record.entity_type)
        aliases.append(record)

    entity_verse_links: list[EntityVerseLinkRecord] = []
    for row in _load_fixture(fixtures_dir / "entity_verse_links.json"):
        record = EntityVerseLinkRecord.model_validate(row)
        _validate_entity_type(record.entity_type)
        entity_verse_links.append(record)

    relationships: list[EntityRelationshipRecord] = []
    for row in _load_fixture(fixtures_dir / "relationships.json"):
        record = EntityRelationshipRecord.model_validate(row)
        _validate_entity_type(record.source_type)
        _validate_entity_type(record.target_type)
        _validate_relation_type(record.relation_type)
        relationships.append(record)

    return MetadataBundle(
        people=people,
        places=places,
        events=events,
        aliases=aliases,
        entity_verse_links=entity_verse_links,
        relationships=relationships,
    )
