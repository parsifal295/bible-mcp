import json
from pathlib import Path

from bible_mcp.vendor.metadata_overlay import load_metadata_overlay
from bible_mcp.vendor.theographic_normalizer import (
    normalize_theographic_snapshot,
    reference_from_osis,
)


def _write_json(path: Path, payload: list[dict]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_reference_from_osis_converts_to_runtime_reference() -> None:
    assert reference_from_osis("Gen.12.1") == "Genesis 12:1"
    assert reference_from_osis("Ps.122.2") == "Psalms 122:2"
    assert reference_from_osis("Song.1.1") == "Song of Solomon 1:1"


def test_normalize_theographic_snapshot_builds_bundle_with_overlay_aliases_and_links(
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    _write_json(
        raw_dir / "people.json",
        [
            {
                "id": "row_people_1",
                "fields": {
                    "slug": "abraham_58",
                    "name": "Abram",
                    "displayTitle": "Abraham",
                    "dictionaryText": "Raw Abraham paragraph one.\n\nRaw paragraph two.",
                    "verses": ["verse_gen_12_1", "verse_gen_15_6", "verse_gen_22_2"],
                },
            },
            {
                "id": "unnamed_1",
                "fields": {
                    "slug": "eliezer-of-damascus",
                    "name": "Eliezer",
                    "dictText": "Steward of Abraham.\n\nSecond paragraph should be ignored.",
                    "verses": ["verse_gen_15_2"],
                },
            },
            {
                "id": "unnamed_2",
                "fields": {
                    "slug": "list-person",
                    "name": "List Person",
                    "dictText": [
                        "First list entry.\n\nSecond paragraph should be ignored.",
                        "Backup entry should not be used.",
                    ],
                    "verses": [],
                },
            },
        ],
    )
    _write_json(
        raw_dir / "places.json",
        [
            {
                "id": "row_place_1",
                "fields": {
                    "slug": "jerusalem_636",
                    "displayTitle": "Jerusalem",
                    "esvName": "Jerusalem",
                    "kjvName": "Jerusalem",
                    "latitude": "31.778",
                    "longitude": "35.235",
                    "verses": ["verse_ps_122_2", "verse_lk_2_22", "verse_mt_5_35"],
                },
            },
            {
                "id": "unknown_place_1",
                "fields": {
                    "slug": "mamre",
                    "displayTitle": "Mamre",
                    "verses": ["verse_gen_13_18"],
                },
            },
        ],
    )
    _write_json(
        raw_dir / "events.json",
        [
            {
                "id": "binding_event",
                "fields": {
                    "eventID": 77,
                    "title": "Binding of Isaac",
                    "verses": ["verse_gen_22_2", "verse_gen_22_9"],
                },
            }
        ],
    )
    _write_json(
        raw_dir / "verses.json",
        [
            {"id": "verse_gen_12_1", "fields": {"osisRef": "Gen.12.1"}},
            {"id": "verse_gen_15_6", "fields": {"osisRef": "Gen.15.6"}},
            {"id": "verse_gen_22_2", "fields": {"osisRef": "Gen.22.2"}},
            {"id": "verse_gen_15_2", "fields": {"osisRef": "Gen.15.2"}},
            {"id": "verse_ps_122_2", "fields": {"osisRef": "Ps.122.2"}},
            {"id": "verse_lk_2_22", "fields": {"osisRef": "Luke.2.22"}},
            {"id": "verse_mt_5_35", "fields": {"osisRef": "Matt.5.35"}},
            {"id": "verse_gen_13_18", "fields": {"osisRef": "Gen.13.18"}},
            {"id": "verse_gen_22_9", "fields": {"osisRef": "Gen.22.9"}},
        ],
    )

    bundle = normalize_theographic_snapshot(
        tmp_path,
        overlay=load_metadata_overlay(),
        link_limit=2,
    )

    people = {row.slug: row for row in bundle.people}
    places = {row.slug: row for row in bundle.places}
    events = {row.slug: row for row in bundle.events}

    assert people["abraham"].display_name == "아브라함"
    assert people["abraham"].description
    assert people["eliezer-of-damascus"].description == "Steward of Abraham."
    assert people["list-person"].description == "First list entry."

    assert places["jerusalem"].display_name == "예루살렘"
    assert places["jerusalem"].latitude == 31.778
    assert places["jerusalem"].longitude == 35.235
    assert places["mamre"].display_name == "Mamre"

    assert events["binding-of-isaac-77"].display_name == "Binding of Isaac"

    alias_rows = {
        (row.entity_type, row.entity_slug, row.alias) for row in bundle.aliases
    }
    assert ("people", "abraham", "Abram") in alias_rows
    assert ("people", "abraham", "Abraham") in alias_rows
    assert ("people", "abraham", "아브람") in alias_rows
    assert ("places", "jerusalem", "Jerusalem") in alias_rows

    verse_links = [
        (row.entity_type, row.entity_slug, row.reference)
        for row in bundle.entity_verse_links
    ]
    assert verse_links.count(("people", "abraham", "Genesis 12:1")) == 1
    assert verse_links.count(("people", "abraham", "Genesis 15:6")) == 1
    assert ("people", "abraham", "Genesis 22:2") not in verse_links
    assert verse_links.count(("places", "jerusalem", "Psalms 122:2")) == 1
    assert verse_links.count(("places", "jerusalem", "Luke 2:22")) == 1
    assert ("places", "jerusalem", "Matthew 5:35") not in verse_links

    assert bundle.relationships == []
