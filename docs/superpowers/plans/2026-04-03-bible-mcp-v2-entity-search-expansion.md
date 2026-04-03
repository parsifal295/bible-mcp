# Bible MCP V2 Entity Search Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand `search_entities` so explicit `entity_type=places|events` searches work while default search remains people-only.

**Architecture:** Keep the current importer and MCP tool surface intact, but ship non-empty bundled `places` and `events` fixtures so the runtime has real data to search. Refactor `EntityService` around a small type registry so exact-match lookup rules stay shared across `people`, `places`, and `events` without widening default search scope.

**Tech Stack:** Python, SQLite, FastMCP, pytest

---

## File Structure

- Modify: `src/bible_mcp/metadata/fixtures/places.json`
  Repository-managed bundled place records used by default metadata import.
- Modify: `src/bible_mcp/metadata/fixtures/events.json`
  Repository-managed bundled event records used by default metadata import.
- Modify: `src/bible_mcp/metadata/fixtures/aliases.json`
  Shared alias fixture file; extend it with `places` and `events` aliases.
- Modify: `src/bible_mcp/services/entity_service.py`
  Refactor search logic from hard-coded people-only SQL into a type-registry-driven exact-match search path.
- Modify: `tests/test_metadata_loader.py`
  Assert the default fixture bundle now contains representative places, events, and aliases.
- Modify: `tests/test_metadata_importer.py`
  Assert importing the default bundle populates place and event rows in SQLite.
- Modify: `tests/test_entity_service.py`
  Add service-level regressions for default people-only behavior and explicit place/event searches.
- Modify: `tests/test_mcp_tools.py`
  Add an MCP handler regression using the real `EntityService` plus imported default fixtures.
- Modify: `README.md`
  Document that place and event lookup requires explicit `entity_type`.

### Task 1: Ship bundled place and event fixtures

**Files:**
- Modify: `src/bible_mcp/metadata/fixtures/places.json`
- Modify: `src/bible_mcp/metadata/fixtures/events.json`
- Modify: `src/bible_mcp/metadata/fixtures/aliases.json`
- Test: `tests/test_metadata_loader.py`
- Test: `tests/test_metadata_importer.py`

- [ ] **Step 1: Write the failing fixture and importer tests**

Add a stronger default-bundle assertion in `tests/test_metadata_loader.py` and a default-bundle importer regression in `tests/test_metadata_importer.py`.

```python
def test_default_fixture_bundle_contains_representative_people_places_events_and_relationships() -> None:
    bundle = load_metadata_fixtures()

    people_slugs = {person.slug for person in bundle.people}
    place_slugs = {place.slug for place in bundle.places}
    event_slugs = {event.slug for event in bundle.events}

    assert {"abraham", "isaac", "jacob", "jesse", "david", "jesus", "peter", "john"} <= people_slugs
    assert {"jerusalem", "bethlehem", "nazareth", "galilee", "jordan-river"} <= place_slugs
    assert {"exodus", "crucifixion", "resurrection"} <= event_slugs

    alias_pairs = {(alias.entity_type, alias.entity_slug, alias.alias) for alias in bundle.aliases}
    assert ("places", "jerusalem", "Jerusalem") in alias_pairs
    assert ("places", "nazareth", "Nazareth") in alias_pairs
    assert ("events", "resurrection", "Resurrection") in alias_pairs
    assert ("events", "crucifixion", "십자가 사건") in alias_pairs


def test_import_metadata_fixtures_imports_default_bundle_places_and_events(tmp_path: Path) -> None:
    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)

    import_metadata_fixtures(conn)

    places = conn.execute(
        "select slug, display_name from places order by slug"
    ).fetchall()
    events = conn.execute(
        "select slug, display_name from events order by slug"
    ).fetchall()

    assert ("jerusalem", "예루살렘") in [tuple(row) for row in places]
    assert ("bethlehem", "베들레헴") in [tuple(row) for row in places]
    assert ("resurrection", "부활") in [tuple(row) for row in events]
    assert ("crucifixion", "십자가 처형") in [tuple(row) for row in events]
```

- [ ] **Step 2: Run the targeted tests to confirm the current bundle is too narrow**

Run:

```bash
python -m pytest tests/test_metadata_loader.py::test_default_fixture_bundle_contains_representative_people_places_events_and_relationships -v
python -m pytest tests/test_metadata_importer.py::test_import_metadata_fixtures_imports_default_bundle_places_and_events -v
```

Expected:

```text
FAIL ... assert {"jerusalem", ...} <= place_slugs
FAIL ... assert ("jerusalem", "예루살렘") in []
```

- [ ] **Step 3: Populate the bundled fixture files with the minimal shipped dataset**

Replace the empty place and event fixture arrays and extend aliases with explicit place/event aliases.

`src/bible_mcp/metadata/fixtures/places.json`

```json
[
  {"slug": "bethlehem", "display_name": "베들레헴", "latitude": 31.7054, "longitude": 35.2024},
  {"slug": "galilee", "display_name": "갈릴리", "latitude": 32.8333, "longitude": 35.5833},
  {"slug": "jerusalem", "display_name": "예루살렘", "latitude": 31.7780, "longitude": 35.2350},
  {"slug": "jordan-river", "display_name": "요단강", "latitude": 31.8500, "longitude": 35.5500},
  {"slug": "nazareth", "display_name": "나사렛", "latitude": 32.6996, "longitude": 35.3035}
]
```

`src/bible_mcp/metadata/fixtures/events.json`

```json
[
  {"slug": "crucifixion", "display_name": "십자가 처형", "description": "예수의 십자가 죽음 사건"},
  {"slug": "exodus", "display_name": "출애굽", "description": "이스라엘이 애굽을 떠난 구원 사건"},
  {"slug": "resurrection", "display_name": "부활", "description": "예수의 부활 사건"}
]
```

Append to `src/bible_mcp/metadata/fixtures/aliases.json`:

```json
[
  {"entity_type": "places", "entity_slug": "bethlehem", "alias": "Bethlehem"},
  {"entity_type": "places", "entity_slug": "galilee", "alias": "Galilee"},
  {"entity_type": "places", "entity_slug": "jerusalem", "alias": "Jerusalem"},
  {"entity_type": "places", "entity_slug": "jordan-river", "alias": "Jordan River"},
  {"entity_type": "places", "entity_slug": "nazareth", "alias": "Nazareth"},
  {"entity_type": "events", "entity_slug": "crucifixion", "alias": "Crucifixion"},
  {"entity_type": "events", "entity_slug": "crucifixion", "alias": "십자가 사건"},
  {"entity_type": "events", "entity_slug": "exodus", "alias": "Exodus"},
  {"entity_type": "events", "entity_slug": "resurrection", "alias": "Resurrection"}
]
```

- [ ] **Step 4: Re-run the fixture and importer tests**

Run:

```bash
python -m pytest tests/test_metadata_loader.py::test_default_fixture_bundle_contains_representative_people_places_events_and_relationships -v
python -m pytest tests/test_metadata_importer.py::test_import_metadata_fixtures_imports_default_bundle_places_and_events -v
```

Expected:

```text
PASSED
PASSED
```

- [ ] **Step 5: Commit the fixture bundle expansion**

Run:

```bash
git add src/bible_mcp/metadata/fixtures/places.json src/bible_mcp/metadata/fixtures/events.json src/bible_mcp/metadata/fixtures/aliases.json tests/test_metadata_loader.py tests/test_metadata_importer.py
git commit -m "feat: ship bundled place and event fixtures"
```

### Task 2: Refactor `EntityService` for typed place and event search

**Files:**
- Modify: `src/bible_mcp/services/entity_service.py`
- Test: `tests/test_entity_service.py`
- Test: `tests/test_mcp_tools.py`

- [ ] **Step 1: Write the failing service and MCP regressions**

Add one service test to lock default people-only behavior, one service test to lock typed search, and one MCP regression that uses the real service plus the default imported bundle.

```python
def test_search_keeps_default_scope_people_only_with_bundled_place_aliases(tmp_path) -> None:
    conn, service = _build_service(tmp_path)
    import_metadata_fixtures(conn)

    assert service.search("Jerusalem", limit=5) == []


@pytest.mark.parametrize(
    ("query", "entity_type", "expected"),
    [
        (
            "Jerusalem",
            "places",
            {
                "entity_type": "places",
                "slug": "jerusalem",
                "display_name": "예루살렘",
                "description": None,
                "matched_by": "alias",
            },
        ),
        (
            "Resurrection",
            "events",
            {
                "entity_type": "events",
                "slug": "resurrection",
                "display_name": "부활",
                "description": "예수의 부활 사건",
                "matched_by": "alias",
            },
        ),
    ],
)
def test_search_resolves_bundled_place_and_event_aliases(tmp_path, query, entity_type, expected) -> None:
    conn, service = _build_service(tmp_path)
    import_metadata_fixtures(conn)

    assert service.search(query, entity_type=entity_type, limit=1) == [expected]


def test_search_entities_handler_returns_place_results_with_real_entity_service(tmp_path) -> None:
    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)
    import_metadata_fixtures(conn)
    handlers = build_tool_handlers(
        FakeSearchService(),
        FakePassageService(),
        None,
        Mock(),
        EntityService(conn),
        None,
    )

    result = handlers["search_entities"](
        {"query": "Jerusalem", "entity_type": "places", "limit": 1}
    )

    assert result["results"] == [
        {
            "entity_type": "places",
            "slug": "jerusalem",
            "display_name": "예루살렘",
            "description": None,
            "matched_by": "alias",
        }
    ]
```

- [ ] **Step 2: Run the targeted regressions to confirm people-only search is still blocking typed results**

Run:

```bash
python -m pytest tests/test_entity_service.py::test_search_keeps_default_scope_people_only_with_bundled_place_aliases -v
python -m pytest tests/test_entity_service.py::test_search_resolves_bundled_place_and_event_aliases -v
python -m pytest tests/test_mcp_tools.py::test_search_entities_handler_returns_place_results_with_real_entity_service -v
```

Expected:

```text
PASSED
FAIL ... assert [] == [{"entity_type": "places", ...}]
FAIL ... assert [] == [{"entity_type": "places", ...}]
```

- [ ] **Step 3: Implement a typed registry inside `EntityService`**

Refactor `src/bible_mcp/services/entity_service.py` so the service picks a search config per entity type and reuses the same exact-match loop for all supported types.

```python
from __future__ import annotations


ENTITY_SEARCH_CONFIG = {
    "people": {
        "table": "people",
        "display_name_column": "display_name",
        "slug_column": "slug",
        "description_sql": "description",
        "supports_aliases": True,
    },
    "places": {
        "table": "places",
        "display_name_column": "display_name",
        "slug_column": "slug",
        "description_sql": "null",
        "supports_aliases": True,
    },
    "events": {
        "table": "events",
        "display_name_column": "display_name",
        "slug_column": "slug",
        "description_sql": "description",
        "supports_aliases": True,
    },
}


class EntityService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def search(self, query: str, entity_type: str | None = None, limit: int = 5):
        limit = int(limit)
        if limit < 1:
            raise ValueError("limit must be at least 1")

        search_types = [entity_type] if entity_type is not None else ["people"]
        match_priority = {"display_name": 0, "alias": 1, "slug": 2}
        candidates: dict[tuple[str, str], dict] = {}

        for current_type in search_types:
            config = ENTITY_SEARCH_CONFIG.get(current_type)
            if config is None:
                continue
            for matched_by, sql in self._match_queries(current_type, config):
                for row in self.conn.execute(sql, (query,)).fetchall():
                    candidate = {
                        "entity_type": row["entity_type"],
                        "slug": row["slug"],
                        "display_name": row["display_name"],
                        "description": row["description"],
                        "matched_by": matched_by,
                        "_rank": match_priority[matched_by],
                    }
                    identity = (candidate["entity_type"], candidate["slug"])
                    existing = candidates.get(identity)
                    if existing is None or candidate["_rank"] < existing["_rank"]:
                        candidates[identity] = candidate

        ordered = sorted(
            candidates.values(),
            key=lambda candidate: (candidate["_rank"], candidate["display_name"], candidate["slug"]),
        )
        return [{key: value for key, value in candidate.items() if key != "_rank"} for candidate in ordered[:limit]]

    def _match_queries(self, entity_type: str, config: dict[str, object]):
        table = config["table"]
        display_name_column = config["display_name_column"]
        slug_column = config["slug_column"]
        description_sql = config["description_sql"]
        queries = [
            (
                "display_name",
                f\"\"\"
                select '{entity_type}' as entity_type, {slug_column} as slug, {display_name_column} as display_name, {description_sql} as description
                from {table}
                where {display_name_column} = ?
                order by {display_name_column}, {slug_column}
                \"\"\",
            ),
            (
                "slug",
                f\"\"\"
                select '{entity_type}' as entity_type, {slug_column} as slug, {display_name_column} as display_name, {description_sql} as description
                from {table}
                where {slug_column} = ?
                order by {display_name_column}, {slug_column}
                \"\"\",
            ),
        ]
        if config["supports_aliases"]:
            queries.insert(
                1,
                (
                    "alias",
                    f\"\"\"
                    select '{entity_type}' as entity_type, e.{slug_column} as slug, e.{display_name_column} as display_name, {description_sql} as description
                    from {table} e
                    join entity_aliases a
                      on a.entity_type = '{entity_type}' and a.entity_slug = e.{slug_column}
                    where a.alias = ?
                    order by e.{display_name_column}, e.{slug_column}
                    \"\"\",
                ),
            )
        return tuple(queries)
```

- [ ] **Step 4: Re-run the service and MCP regressions**

Run:

```bash
python -m pytest tests/test_entity_service.py -v
python -m pytest tests/test_mcp_tools.py::test_search_entities_handler_returns_place_results_with_real_entity_service -v
```

Expected:

```text
all selected tests PASSED
```

- [ ] **Step 5: Commit the typed search refactor**

Run:

```bash
git add src/bible_mcp/services/entity_service.py tests/test_entity_service.py tests/test_mcp_tools.py
git commit -m "feat: expand entity search to places and events"
```

### Task 3: Document the explicit typed-search contract and run full verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the README to describe the new search boundary**

Add one short paragraph under the V2 metadata description so readers know default search is still people-only.

```md
V2 entity search defaults to `people` for backwards compatibility. To search bundled place or event metadata, call `search_entities` with an explicit `entity_type` such as `places` or `events`.
```

- [ ] **Step 2: Run the focused docs and regression commands**

Run:

```bash
python -m pytest tests/test_metadata_loader.py tests/test_metadata_importer.py tests/test_entity_service.py tests/test_mcp_tools.py -q
```

Expected:

```text
all selected tests PASSED
```

- [ ] **Step 3: Run the full suite**

Run:

```bash
python -m pytest -q
```

Expected:

```text
all tests PASSED
```

- [ ] **Step 4: Commit the README and verification completion**

Run:

```bash
git add README.md
git commit -m "docs: document typed entity search scope"
```
