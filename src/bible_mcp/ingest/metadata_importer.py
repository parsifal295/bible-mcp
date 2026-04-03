from __future__ import annotations

import sqlite3
from pathlib import Path

from bible_mcp.domain.metadata import ENTITY_TYPES
from bible_mcp.metadata.loader import DEFAULT_FIXTURE_DIR, load_metadata_fixtures
from bible_mcp.services.passage_service import PassageService


METADATA_TABLES = (
    "entity_relationships",
    "entity_aliases",
    "entity_verse_links",
    "people",
    "places",
    "events",
)


def _entity_lookup(bundle) -> dict[str, set[str]]:
    return {
        "people": {row.slug for row in bundle.people},
        "places": {row.slug for row in bundle.places},
        "events": {row.slug for row in bundle.events},
    }


def _require_entity(entity_lookup: dict[str, set[str]], entity_type: str, entity_slug: str, context: str) -> None:
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"Unknown entity_type in {context}: {entity_type}")
    if entity_slug not in entity_lookup[entity_type]:
        raise ValueError(f"missing {context.lower()} entity: {entity_type}/{entity_slug}")


def _validate_bundle(conn: sqlite3.Connection, bundle) -> None:
    entity_lookup = _entity_lookup(bundle)
    passage_service = PassageService(conn)

    for alias in bundle.aliases:
        _require_entity(
            entity_lookup,
            alias.entity_type,
            alias.entity_slug,
            "Alias",
        )

    for link in bundle.entity_verse_links:
        _require_entity(
            entity_lookup,
            link.entity_type,
            link.entity_slug,
            "Entity verse link",
        )
        try:
            passage_service.lookup(link.reference)
        except (LookupError, ValueError) as exc:
            raise type(exc)(f"Entity verse link reference: {exc}") from exc

    for relationship in bundle.relationships:
        _require_entity(
            entity_lookup,
            relationship.source_type,
            relationship.source_slug,
            "Relationship source",
        )
        _require_entity(
            entity_lookup,
            relationship.target_type,
            relationship.target_slug,
            "Relationship target",
        )


def _delete_metadata_rows(conn: sqlite3.Connection) -> None:
    for table in METADATA_TABLES:
        conn.execute(f"delete from {table}")


def import_metadata_fixtures(
    conn: sqlite3.Connection,
    fixtures_dir: Path = DEFAULT_FIXTURE_DIR,
) -> None:
    """Import repo-managed metadata fixtures into an existing schema.

    The caller is responsible for ensuring the metadata tables already exist.
    This function manages an import-local savepoint so failures roll back only
    the metadata import without committing or disturbing any caller-owned outer
    transaction.
    """
    bundle = load_metadata_fixtures(fixtures_dir)
    _validate_bundle(conn, bundle)

    conn.execute("savepoint metadata_import")
    try:
        _delete_metadata_rows(conn)

        conn.executemany(
            "insert into people(slug, display_name, description) values (?, ?, ?)",
            ((row.slug, row.display_name, row.description) for row in bundle.people),
        )
        conn.executemany(
            "insert into places(slug, display_name, latitude, longitude) values (?, ?, ?, ?)",
            (
                (row.slug, row.display_name, row.latitude, row.longitude)
                for row in bundle.places
            ),
        )
        conn.executemany(
            "insert into events(slug, display_name, description) values (?, ?, ?)",
            ((row.slug, row.display_name, row.description) for row in bundle.events),
        )
        conn.executemany(
            "insert into entity_aliases(entity_type, entity_slug, alias) values (?, ?, ?)",
            ((row.entity_type, row.entity_slug, row.alias) for row in bundle.aliases),
        )
        conn.executemany(
            "insert into entity_verse_links(entity_type, entity_slug, reference) values (?, ?, ?)",
            (
                (row.entity_type, row.entity_slug, row.reference)
                for row in bundle.entity_verse_links
            ),
        )
        conn.executemany(
            """
            insert into entity_relationships(
                source_type,
                source_slug,
                relation_type,
                target_type,
                target_slug,
                is_primary,
                note
            )
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    row.source_type,
                    row.source_slug,
                    row.relation_type,
                    row.target_type,
                    row.target_slug,
                    int(row.is_primary),
                    row.note,
                )
                for row in bundle.relationships
            ),
        )
    except Exception:
        conn.execute("rollback to metadata_import")
        conn.execute("release metadata_import")
        raise
    else:
        conn.execute("release metadata_import")
