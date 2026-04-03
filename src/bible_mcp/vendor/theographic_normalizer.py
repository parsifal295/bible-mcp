import json
import re
from pathlib import Path

from bible_mcp.metadata.models import (
    EntityAliasRecord,
    EntityRelationshipRecord,
    EntityVerseLinkRecord,
    MetadataBundle,
    MetadataEntity,
    PlaceRecord,
)
from bible_mcp.vendor.metadata_overlay import MetadataOverlay


_OSIS_BOOKS = {
    "Gen": "Genesis",
    "Exod": "Exodus",
    "Lev": "Leviticus",
    "Num": "Numbers",
    "Deut": "Deuteronomy",
    "Josh": "Joshua",
    "Judg": "Judges",
    "Ruth": "Ruth",
    "1Sam": "1 Samuel",
    "2Sam": "2 Samuel",
    "1Kgs": "1 Kings",
    "2Kgs": "2 Kings",
    "1Chr": "1 Chronicles",
    "2Chr": "2 Chronicles",
    "Ezra": "Ezra",
    "Neh": "Nehemiah",
    "Esth": "Esther",
    "Job": "Job",
    "Ps": "Psalms",
    "Prov": "Proverbs",
    "Eccl": "Ecclesiastes",
    "Song": "Song of Solomon",
    "Isa": "Isaiah",
    "Jer": "Jeremiah",
    "Lam": "Lamentations",
    "Ezek": "Ezekiel",
    "Dan": "Daniel",
    "Hos": "Hosea",
    "Joel": "Joel",
    "Amos": "Amos",
    "Obad": "Obadiah",
    "Jonah": "Jonah",
    "Mic": "Micah",
    "Nah": "Nahum",
    "Hab": "Habakkuk",
    "Zeph": "Zephaniah",
    "Hag": "Haggai",
    "Zech": "Zechariah",
    "Mal": "Malachi",
    "Matt": "Matthew",
    "Mark": "Mark",
    "Luke": "Luke",
    "John": "John",
    "Acts": "Acts",
    "Rom": "Romans",
    "1Cor": "1 Corinthians",
    "2Cor": "2 Corinthians",
    "Gal": "Galatians",
    "Eph": "Ephesians",
    "Phil": "Philippians",
    "Col": "Colossians",
    "1Thess": "1 Thessalonians",
    "2Thess": "2 Thessalonians",
    "1Tim": "1 Timothy",
    "2Tim": "2 Timothy",
    "Titus": "Titus",
    "Phlm": "Philemon",
    "Heb": "Hebrews",
    "Jas": "James",
    "1Pet": "1 Peter",
    "2Pet": "2 Peter",
    "1John": "1 John",
    "2John": "2 John",
    "3John": "3 John",
    "Jude": "Jude",
    "Rev": "Revelation",
}


def reference_from_osis(osis_ref: str) -> str:
    chunks = osis_ref.split(".")
    if len(chunks) < 3:
        return osis_ref
    book = _OSIS_BOOKS.get(chunks[0], chunks[0])
    chapter = chunks[1]
    verse = chunks[2]
    return f"{book} {chapter}:{verse}"


def normalize_theographic_snapshot(
    snapshot_dir: Path,
    overlay: MetadataOverlay,
    link_limit: int = 20,
) -> MetadataBundle:
    raw_dir = snapshot_dir / "raw"
    people_rows = _load_rows(raw_dir / "people.json")
    place_rows = _load_rows(raw_dir / "places.json")
    event_rows = _load_rows(raw_dir / "events.json")
    verse_rows = _load_rows(raw_dir / "verses.json")
    verse_lookup = _build_verse_lookup(verse_rows)

    people: list[MetadataEntity] = []
    places: list[PlaceRecord] = []
    events: list[MetadataEntity] = []
    aliases: list[EntityAliasRecord] = []
    links: list[EntityVerseLinkRecord] = []
    relationship_fields: list[tuple[str, dict]] = []
    id_to_slug: dict[str, str] = {}
    gender_by_slug: dict[str, str] = {}

    for row in people_rows:
        fields = _fields(row)
        source_slug = _string(fields.get("slug"))
        if not source_slug:
            continue
        rule = overlay.people.get(source_slug)
        entity_slug = rule.canonical_slug if rule else source_slug
        display_name = (
            rule.display_name
            if rule
            else _first_non_empty(fields.get("displayTitle"), fields.get("name"), entity_slug)
        )
        description = rule.description if rule and rule.description else _first_paragraph(fields)
        people.append(
            MetadataEntity(
                slug=entity_slug,
                display_name=display_name,
                description=description,
            )
        )
        row_id = _string(row.get("id"))
        if row_id:
            id_to_slug[row_id] = entity_slug
        gender = _normalize_gender(fields.get("gender"))
        if gender:
            gender_by_slug[entity_slug] = gender
        relationship_fields.append((entity_slug, fields))

        alias_values = _alias_values(
            fields.get("displayTitle"),
            fields.get("name"),
            *([] if rule is None else rule.aliases),
        )
        aliases.extend(_build_alias_rows("people", entity_slug, alias_values))
        links.extend(
            _build_link_rows(
                "people",
                entity_slug,
                fields.get("verses"),
                verse_lookup,
                link_limit,
            )
        )

    for row in place_rows:
        fields = _fields(row)
        source_slug = _string(fields.get("slug"))
        if not source_slug:
            continue
        rule = overlay.places.get(source_slug)
        entity_slug = rule.canonical_slug if rule else source_slug
        display_name = (
            rule.display_name
            if rule
            else _first_non_empty(
                fields.get("displayTitle"),
                fields.get("esvName"),
                fields.get("kjvName"),
                entity_slug,
            )
        )
        places.append(
            PlaceRecord(
                slug=entity_slug,
                display_name=display_name,
                latitude=_to_float(fields.get("latitude")),
                longitude=_to_float(fields.get("longitude")),
            )
        )

        alias_values = _alias_values(
            fields.get("displayTitle"),
            fields.get("esvName"),
            fields.get("kjvName"),
            *([] if rule is None else rule.aliases),
        )
        aliases.extend(_build_alias_rows("places", entity_slug, alias_values))
        links.extend(
            _build_link_rows(
                "places",
                entity_slug,
                fields.get("verses"),
                verse_lookup,
                link_limit,
            )
        )

    for row in event_rows:
        fields = _fields(row)
        title = _string(fields.get("title"))
        if not title:
            continue
        slug = _string(fields.get("slug")) or _event_slug(title, fields.get("eventID"))
        events.append(
            MetadataEntity(
                slug=slug,
                display_name=title,
                description=_first_paragraph(fields),
            )
        )
        aliases.extend(_build_alias_rows("events", slug, _alias_values(title)))
        links.extend(
            _build_link_rows(
                "events",
                slug,
                fields.get("verses"),
                verse_lookup,
                link_limit,
            )
        )

    relationships = _build_people_relationships(relationship_fields, id_to_slug, gender_by_slug)

    return MetadataBundle(
        people=people,
        places=places,
        events=events,
        aliases=aliases,
        entity_verse_links=links,
        relationships=relationships,
    )


def _load_rows(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Theographic raw payload must be a list: {path}")
    return payload


def _fields(row: dict) -> dict:
    fields = row.get("fields")
    if isinstance(fields, dict):
        return fields
    return {}


def _string(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _first_non_empty(*values: object) -> str:
    for value in values:
        text = _string(value)
        if text:
            return text
    return ""


def _first_paragraph(fields: dict) -> str | None:
    text = _first_non_empty_text_value(fields.get("dictionaryText"), fields.get("dictText"))
    if not text:
        return None
    return re.split(r"\n\s*\n", text, maxsplit=1)[0].strip() or None


def _first_non_empty_text_value(*values: object) -> str:
    for value in values:
        text = _to_text(value)
        if text:
            return text
    return ""


def _to_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    return text
    return ""


def _event_slug(title: str, event_id: object) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not base:
        base = "event"
    if event_id is None:
        return base
    return f"{base}-{event_id}"


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _alias_values(*values: object) -> list[str]:
    dedup: dict[str, str] = {}
    for value in values:
        text = _string(value)
        if not text:
            continue
        key = text.casefold()
        if key not in dedup:
            dedup[key] = text
    return list(dedup.values())


def _build_alias_rows(entity_type: str, entity_slug: str, aliases: list[str]) -> list[EntityAliasRecord]:
    return [
        EntityAliasRecord(
            entity_type=entity_type,
            entity_slug=entity_slug,
            alias=alias,
        )
        for alias in aliases
    ]


def _build_verse_lookup(verse_rows: list[dict]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in verse_rows:
        verse_id = _string(row.get("id"))
        if not verse_id:
            continue
        fields = _fields(row)
        osis_ref = _string(fields.get("osisRef"))
        if not osis_ref:
            continue
        lookup[verse_id] = reference_from_osis(osis_ref)
    return lookup


def _build_link_rows(
    entity_type: str,
    entity_slug: str,
    verse_ids: object,
    verse_lookup: dict[str, str],
    link_limit: int,
) -> list[EntityVerseLinkRecord]:
    if not isinstance(verse_ids, list):
        return []
    rows: list[EntityVerseLinkRecord] = []
    seen: set[str] = set()
    for value in verse_ids:
        verse_id = _string(value)
        if not verse_id:
            continue
        reference = verse_lookup.get(verse_id)
        if not reference or reference in seen:
            continue
        seen.add(reference)
        rows.append(
            EntityVerseLinkRecord(
                entity_type=entity_type,
                entity_slug=entity_slug,
                reference=reference,
            )
        )
        if len(rows) >= link_limit:
            break
    return rows


def _build_people_relationships(
    relationship_fields: list[tuple[str, dict]],
    id_to_slug: dict[str, str],
    gender_by_slug: dict[str, str],
) -> list[EntityRelationshipRecord]:
    known_slugs = set(id_to_slug.values())
    dedup: dict[tuple[str, str, str], EntityRelationshipRecord] = {}

    for source_slug, fields in relationship_fields:
        for parent_slug in _resolve_related_slugs(fields.get("father"), id_to_slug, known_slugs):
            _append_parent_child_rows(dedup, gender_by_slug, parent_slug, source_slug, "father")

        for parent_slug in _resolve_related_slugs(fields.get("mother"), id_to_slug, known_slugs):
            _append_parent_child_rows(dedup, gender_by_slug, parent_slug, source_slug, "mother")

        parent_gender = gender_by_slug.get(source_slug)
        parent_relation = "father" if parent_gender == "male" else "mother" if parent_gender == "female" else "father"
        for child_slug in _resolve_related_slugs(fields.get("children"), id_to_slug, known_slugs):
            _append_relationship(dedup, source_slug, parent_relation, child_slug)
            _append_relationship(dedup, source_slug, "child", child_slug)
            child_relation = _child_relation_type(gender_by_slug.get(child_slug))
            if child_relation:
                _append_relationship(dedup, source_slug, child_relation, child_slug)

        for partner_slug in _resolve_related_slugs(fields.get("partners"), id_to_slug, known_slugs):
            _append_relationship(dedup, source_slug, "spouse", partner_slug)
            _append_relationship(dedup, partner_slug, "spouse", source_slug)

        for sibling_slug in _resolve_related_slugs(fields.get("siblings"), id_to_slug, known_slugs):
            sibling_relation = _sibling_relation_type(gender_by_slug.get(sibling_slug))
            if sibling_relation:
                _append_relationship(dedup, source_slug, sibling_relation, sibling_slug)
            reciprocal_relation = _sibling_relation_type(gender_by_slug.get(source_slug))
            if reciprocal_relation:
                _append_relationship(dedup, sibling_slug, reciprocal_relation, source_slug)

    return list(dedup.values())


def _append_parent_child_rows(
    dedup: dict[tuple[str, str, str], EntityRelationshipRecord],
    gender_by_slug: dict[str, str],
    parent_slug: str,
    child_slug: str,
    parent_relation: str,
) -> None:
    _append_relationship(dedup, parent_slug, parent_relation, child_slug)
    _append_relationship(dedup, parent_slug, "child", child_slug)
    child_relation = _child_relation_type(gender_by_slug.get(child_slug))
    if child_relation:
        _append_relationship(dedup, parent_slug, child_relation, child_slug)


def _append_relationship(
    dedup: dict[tuple[str, str, str], EntityRelationshipRecord],
    source_slug: str,
    relation_type: str,
    target_slug: str,
) -> None:
    key = (source_slug, relation_type, target_slug)
    if key in dedup:
        return
    dedup[key] = EntityRelationshipRecord(
        source_type="people",
        source_slug=source_slug,
        relation_type=relation_type,
        target_type="people",
        target_slug=target_slug,
        is_primary=True,
        note="theographic",
    )


def _resolve_related_slugs(
    values: object,
    id_to_slug: dict[str, str],
    known_slugs: set[str],
) -> list[str]:
    if not isinstance(values, list):
        return []
    dedup: dict[str, str] = {}
    for value in values:
        candidate = _string(value)
        if not candidate:
            continue
        slug = id_to_slug.get(candidate)
        if slug is None and candidate in known_slugs:
            slug = candidate
        if slug is None:
            continue
        dedup[slug] = slug
    return list(dedup.values())


def _normalize_gender(value: object) -> str | None:
    text = _string(value).casefold()
    if text in {"male", "m"}:
        return "male"
    if text in {"female", "f"}:
        return "female"
    return None


def _child_relation_type(gender: str | None) -> str | None:
    if gender == "male":
        return "son"
    if gender == "female":
        return "daughter"
    return None


def _sibling_relation_type(gender: str | None) -> str | None:
    if gender == "male":
        return "brother"
    if gender == "female":
        return "sister"
    return None
