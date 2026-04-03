# Bible MCP V2 Entity Passages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `get_entity_passages` so entity-linked metadata can return representative `reference` and `passage_text` for uniquely resolved people, places, and events.

**Architecture:** Keep `entity_verse_links` as the metadata source of truth, but resolve linked references through the existing `PassageService.lookup()` path instead of duplicating passage parsing and verse assembly. Add one dedicated runtime service for entity-linked passages, expand bundled links across shipped entity types, and wire a new MCP tool without changing the existing search or relation contracts.

**Tech Stack:** Python, SQLite, FastMCP, pytest

---

## File Structure

- Modify: `src/bible_mcp/metadata/fixtures/entity_verse_links.json`
  Expand the bundled representative links from people-only to shipped `people`, `places`, and `events`.
- Modify: `src/bible_mcp/ingest/metadata_importer.py`
  Validate that each linked reference resolves through the same runtime lookup path as `PassageService.lookup()`.
- Create: `src/bible_mcp/services/entity_passage_service.py`
  New runtime service that resolves an entity, handles ambiguity, and returns linked passages with normalized reference text.
- Modify: `src/bible_mcp/mcp_server.py`
  Add handler wiring and MCP registration for `get_entity_passages`.
- Modify: `src/bible_mcp/cli.py`
  Instantiate `EntityPassageService` when optional study tools are available and pass it into the MCP server.
- Modify: `tests/test_metadata_loader.py`
  Assert the default bundled `entity_verse_links` now include representative `people`, `places`, and `events`.
- Modify: `tests/test_metadata_importer.py`
  Seed minimal verse rows for importer tests, assert default-bundle links import correctly, and reject unresolved references.
- Create: `tests/test_entity_passage_service.py`
  Service-level regressions for no match, ambiguity, unique entity passage lookup, and unsupported types.
- Modify: `tests/test_mcp_tools.py`
  Add handler-level and real-service MCP regressions for `get_entity_passages`.

### Task 1: Expand linked passage fixtures and importer validation

**Files:**
- Modify: `src/bible_mcp/metadata/fixtures/entity_verse_links.json`
- Modify: `src/bible_mcp/ingest/metadata_importer.py`
- Modify: `tests/test_metadata_loader.py`
- Modify: `tests/test_metadata_importer.py`

- [ ] **Step 1: Write the failing fixture and importer validation tests**

Extend the default bundle loader test to assert linked references for all shipped active entity types, and add an importer regression that expects unresolved linked references to fail. While editing importer tests, add verse-seeding helpers so importer tests continue to use a runtime-valid `verses` table once reference validation is added.

Use this helper structure in `tests/test_metadata_importer.py`:

```python
MINIMAL_LINK_VERSES = [
    ("KOR", "Genesis", 1, 12, 1, "Genesis 12:1", "OT", "여호와께서 아브람에게 이르시되"),
]

DEFAULT_LINK_VERSES = [
    ("KOR", "Genesis", 1, 12, 1, "Genesis 12:1", "OT", "여호와께서 아브람에게 이르시되"),
    ("KOR", "Genesis", 1, 21, 3, "Genesis 21:3", "OT", "아브라함이 그에게 태어난 아들의 이름을 이삭이라 하였고"),
    ("KOR", "Genesis", 1, 25, 26, "Genesis 25:26", "OT", "후에 나온 아우는 손으로 에서의 발꿈치를 잡았으므로"),
    ("KOR", "1 Samuel", 9, 16, 1, "1 Samuel 16:1", "OT", "여호와께서 사무엘에게 이르시되 내가 이미 사울을 버렸거늘"),
    ("KOR", "1 Samuel", 9, 16, 13, "1 Samuel 16:13", "OT", "사무엘이 기름 뿔병을 가져다가 그의 형제 중에서 그에게 부었더니"),
    ("KOR", "Matthew", 40, 1, 21, "Matthew 1:21", "NT", "아들을 낳으리니 이름을 예수라 하라"),
    ("KOR", "Matthew", 40, 4, 18, "Matthew 4:18", "NT", "갈릴리 해변에 다니시다가 두 형제 곧 베드로라 하는 시몬과"),
    ("KOR", "Matthew", 40, 4, 21, "Matthew 4:21", "NT", "거기서 더 가시다가 다른 두 형제 곧 세베대의 아들 야고보와"),
    ("KOR", "Psalms", 19, 122, 2, "Psalms 122:2", "OT", "예루살렘아 우리 발이 네 성문 안에 섰도다"),
    ("KOR", "Micah", 33, 5, 2, "Micah 5:2", "OT", "베들레헴 에브라다야 너는 유다 족속 중에 작을지라도"),
    ("KOR", "Matthew", 40, 2, 23, "Matthew 2:23", "NT", "나사렛이란 동네에 가서 사니"),
    ("KOR", "Matthew", 40, 4, 15, "Matthew 4:15", "NT", "스불론 땅과 납달리 땅과 요단 강 저편 해변 길과 이방의 갈릴리여"),
    ("KOR", "Matthew", 40, 3, 13, "Matthew 3:13", "NT", "이 때에 예수께서 갈릴리로부터 요단 강에 이르러"),
    ("KOR", "Exodus", 2, 12, 41, "Exodus 12:41", "OT", "사백삼십 년이 끝나는 그 날에 여호와의 군대가 다 애굽 땅에서 나왔은즉"),
    ("KOR", "Matthew", 40, 27, 35, "Matthew 27:35", "NT", "그들이 예수를 십자가에 못 박은 후에"),
    ("KOR", "Matthew", 40, 28, 6, "Matthew 28:6", "NT", "그가 여기 계시지 않고 그가 말씀하시던 대로 살아나셨느니라"),
]


def _seed_verses(conn, rows) -> None:
    conn.executemany(
        '''
        insert into verses(translation, book, book_order, chapter, verse, reference, testament, text)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        rows,
    )
    conn.commit()
```

Update the loader test in `tests/test_metadata_loader.py` to assert link coverage:

```python
link_rows = {(link.entity_type, link.entity_slug, link.reference) for link in bundle.entity_verse_links}
assert {link.entity_type for link in bundle.entity_verse_links} == {"people", "places", "events"}
assert ("places", "jerusalem", "Psalms 122:2") in link_rows
assert ("places", "bethlehem", "Micah 5:2") in link_rows
assert ("events", "resurrection", "Matthew 28:6") in link_rows
assert ("events", "crucifixion", "Matthew 27:35") in link_rows
```

Add a new failing importer test:

```python
def test_import_metadata_fixtures_rejects_unresolvable_entity_verse_reference(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    _write_minimal_metadata_bundle(fixtures)
    _write_fixture(
        fixtures,
        "entity_verse_links.json",
        [{"entity_type": "people", "entity_slug": "abraham", "reference": "Genesis 99:99"}],
    )

    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)
    _seed_verses(conn, MINIMAL_LINK_VERSES)

    with pytest.raises(LookupError, match="Entity verse link reference"):
        import_metadata_fixtures(conn, fixtures_dir=fixtures)
```

Also update the existing importer tests that call `import_metadata_fixtures` so they seed verse rows first:

```python
conn = connect_db(tmp_path / "app.sqlite")
ensure_schema(conn)
_seed_verses(conn, MINIMAL_LINK_VERSES)

import_metadata_fixtures(conn, fixtures_dir=fixtures)
```

And for the default-bundle import regression:

```python
conn = connect_db(tmp_path / "app.sqlite")
ensure_schema(conn)
_seed_verses(conn, DEFAULT_LINK_VERSES)

import_metadata_fixtures(conn)
```

- [ ] **Step 2: Run the targeted tests to confirm the current implementation is missing this validation**

Run:

```bash
.venv/bin/python -m pytest tests/test_metadata_loader.py::test_default_fixture_bundle_contains_representative_people_places_events_and_relationships -v
.venv/bin/python -m pytest tests/test_metadata_importer.py::test_import_metadata_fixtures_rejects_unresolvable_entity_verse_reference -v
```

Expected:

```text
FAILED assertion on `entity_verse_links` entity types
FAILED because no `LookupError` was raised
```

- [ ] **Step 3: Implement the bundled links and importer-side passage validation**

Expand the bundled fixture file and validate links through `PassageService.lookup()`. Use `Psalms 122:2` in the fixture because the current reference parser accepts canonical `Psalms`, not singular `Psalm`.

Update `src/bible_mcp/metadata/fixtures/entity_verse_links.json` to include:

```json
[
  {"entity_type": "people", "entity_slug": "abraham", "reference": "Genesis 12:1"},
  {"entity_type": "people", "entity_slug": "isaac", "reference": "Genesis 21:3"},
  {"entity_type": "people", "entity_slug": "jacob", "reference": "Genesis 25:26"},
  {"entity_type": "people", "entity_slug": "jesse", "reference": "1 Samuel 16:1"},
  {"entity_type": "people", "entity_slug": "david", "reference": "1 Samuel 16:13"},
  {"entity_type": "people", "entity_slug": "jesus", "reference": "Matthew 1:21"},
  {"entity_type": "people", "entity_slug": "peter", "reference": "Matthew 4:18"},
  {"entity_type": "people", "entity_slug": "john", "reference": "Matthew 4:21"},
  {"entity_type": "places", "entity_slug": "jerusalem", "reference": "Psalms 122:2"},
  {"entity_type": "places", "entity_slug": "bethlehem", "reference": "Micah 5:2"},
  {"entity_type": "places", "entity_slug": "nazareth", "reference": "Matthew 2:23"},
  {"entity_type": "places", "entity_slug": "galilee", "reference": "Matthew 4:15"},
  {"entity_type": "places", "entity_slug": "jordan-river", "reference": "Matthew 3:13"},
  {"entity_type": "events", "entity_slug": "exodus", "reference": "Exodus 12:41"},
  {"entity_type": "events", "entity_slug": "crucifixion", "reference": "Matthew 27:35"},
  {"entity_type": "events", "entity_slug": "resurrection", "reference": "Matthew 28:6"}
]
```

Refactor `src/bible_mcp/ingest/metadata_importer.py` like this:

```python
from bible_mcp.services.passage_service import PassageService


def _require_resolvable_reference(passage_service: PassageService, reference: str, context: str) -> None:
    try:
        passage_service.lookup(reference)
    except (LookupError, ValueError) as exc:
        message = f"{context}: {reference}"
        raise type(exc)(message) from exc


def _validate_bundle(conn: sqlite3.Connection, bundle) -> None:
    entity_lookup = _entity_lookup(bundle)
    passage_service = PassageService(conn)

    for alias in bundle.aliases:
        _require_entity(entity_lookup, alias.entity_type, alias.entity_slug, "Alias")

    for link in bundle.entity_verse_links:
        _require_entity(entity_lookup, link.entity_type, link.entity_slug, "Entity verse link")
        _require_resolvable_reference(passage_service, link.reference, "Entity verse link reference")

    for relationship in bundle.relationships:
        _require_entity(entity_lookup, relationship.source_type, relationship.source_slug, "Relationship source")
        _require_entity(entity_lookup, relationship.target_type, relationship.target_slug, "Relationship target")
```

And call it from `import_metadata_fixtures()`:

```python
bundle = load_metadata_fixtures(fixtures_dir)
_validate_bundle(conn, bundle)
```

- [ ] **Step 4: Re-run the importer and loader regressions**

Run:

```bash
.venv/bin/python -m pytest tests/test_metadata_loader.py tests/test_metadata_importer.py -q
```

Expected:

```text
all selected tests PASSED
```

- [ ] **Step 5: Commit the fixture and importer validation work**

Run:

```bash
git add src/bible_mcp/metadata/fixtures/entity_verse_links.json src/bible_mcp/ingest/metadata_importer.py tests/test_metadata_loader.py tests/test_metadata_importer.py
git commit -m "feat: validate and expand entity passage links"
```

### Task 2: Add `EntityPassageService`

**Files:**
- Create: `src/bible_mcp/services/entity_passage_service.py`
- Create: `tests/test_entity_passage_service.py`

- [ ] **Step 1: Write the failing service tests**

Create `tests/test_entity_passage_service.py` with service-focused regressions that seed only the rows needed for each behavior.

Use this test skeleton:

```python
from pathlib import Path

from bible_mcp.db.connection import connect_db
from bible_mcp.db.schema import ensure_schema
from bible_mcp.services.entity_passage_service import EntityPassageService
from bible_mcp.services.entity_service import EntityService
from bible_mcp.services.passage_service import PassageService


def _build_service(tmp_path: Path):
    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)
    return conn, EntityPassageService(conn, EntityService(conn), PassageService(conn))


def _seed_verse(conn, row) -> None:
    conn.execute(
        '''
        insert into verses(translation, book, book_order, chapter, verse, reference, testament, text)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        row,
    )
    conn.commit()
```

Add these tests:

```python
def test_lookup_returns_empty_result_when_no_entity_matches(tmp_path: Path) -> None:
    _, service = _build_service(tmp_path)
    assert service.lookup("missing") == {"resolved_entity": None, "matches": [], "passages": []}


def test_lookup_returns_candidates_without_passages_when_query_is_ambiguous(tmp_path: Path) -> None:
    conn, service = _build_service(tmp_path)
    conn.execute("insert into people(slug, display_name, description) values (?, ?, ?)", ("saul-a", "Saul", "first"))
    conn.execute("insert into people(slug, display_name, description) values (?, ?, ?)", ("saul-b", "Saul", "second"))
    conn.commit()

    result = service.lookup("Saul")

    assert result["resolved_entity"] is None
    assert len(result["matches"]) == 2
    assert result["passages"] == []


def test_lookup_returns_people_linked_passages_for_unique_entity(tmp_path: Path) -> None:
    conn, service = _build_service(tmp_path)
    conn.execute("insert into people(slug, display_name, description) values (?, ?, ?)", ("abraham", "Abraham", "patriarch"))
    conn.execute("insert into entity_aliases(entity_type, entity_slug, alias) values (?, ?, ?)", ("people", "abraham", "아브라함"))
    conn.execute("insert into entity_verse_links(entity_type, entity_slug, reference) values (?, ?, ?)", ("people", "abraham", "Genesis 12:1"))
    _seed_verse(conn, ("KOR", "Genesis", 1, 12, 1, "Genesis 12:1", "OT", "여호와께서 아브람에게 이르시되"))

    result = service.lookup("Abraham")

    assert result == {
        "resolved_entity": {
            "entity_type": "people",
            "slug": "abraham",
            "display_name": "Abraham",
            "description": "patriarch",
            "matched_by": "display_name",
        },
        "matches": [],
        "passages": [{"reference": "Genesis 12:1", "passage_text": "여호와께서 아브람에게 이르시되"}],
    }
```

Also add a parameterized test for place/event plus unsupported type:

```python
@pytest.mark.parametrize(
    ("entity_type", "table", "query", "insert_row", "link_row", "verse_row", "expected"),
    [
        (
            "places",
            "places",
            "예루살렘",
            ("jerusalem", "예루살렘", 31.7780, 35.2350),
            ("places", "jerusalem", "Psalms 122:2"),
            ("KOR", "Psalms", 19, 122, 2, "Psalms 122:2", "OT", "예루살렘아 우리 발이 네 성문 안에 섰도다"),
            {"reference": "Psalms 122:2", "passage_text": "예루살렘아 우리 발이 네 성문 안에 섰도다"},
        ),
        (
            "events",
            "events",
            "부활",
            ("resurrection", "부활", "예수의 부활 사건"),
            ("events", "resurrection", "Matthew 28:6"),
            ("KOR", "Matthew", 40, 28, 6, "Matthew 28:6", "NT", "그가 여기 계시지 않고 살아나셨느니라"),
            {"reference": "Matthew 28:6", "passage_text": "그가 여기 계시지 않고 살아나셨느니라"},
        ),
    ],
)
def test_lookup_returns_linked_passages_for_unique_places_and_events(
    tmp_path: Path,
    entity_type: str,
    table: str,
    query: str,
    insert_row,
    link_row,
    verse_row,
    expected,
) -> None:
    conn, service = _build_service(tmp_path)
    if table == "places":
        conn.execute(
            "insert into places(slug, display_name, latitude, longitude) values (?, ?, ?, ?)",
            insert_row,
        )
    else:
        conn.execute(
            "insert into events(slug, display_name, description) values (?, ?, ?)",
            insert_row,
        )
    conn.execute(
        "insert into entity_verse_links(entity_type, entity_slug, reference) values (?, ?, ?)",
        link_row,
    )
    conn.commit()
    _seed_verse(conn, verse_row)

    result = service.lookup(query, entity_type=entity_type)

    assert result["resolved_entity"]["entity_type"] == entity_type
    assert result["matches"] == []
    assert result["passages"] == [expected]


def test_lookup_returns_empty_result_for_unsupported_entity_type(tmp_path: Path) -> None:
    _, service = _build_service(tmp_path)
    assert service.lookup("Jerusalem", entity_type="angels") == {"resolved_entity": None, "matches": [], "passages": []}
```

- [ ] **Step 2: Run the new service test file to confirm the service does not exist yet**

Run:

```bash
.venv/bin/python -m pytest tests/test_entity_passage_service.py -v
```

Expected:

```text
ERROR `ModuleNotFoundError: No module named 'bible_mcp.services.entity_passage_service'`
```

- [ ] **Step 3: Implement `EntityPassageService`**

Create `src/bible_mcp/services/entity_passage_service.py`:

```python
from __future__ import annotations

from bible_mcp.domain.metadata import ENTITY_TYPES


class EntityPassageService:
    def __init__(self, conn, entity_service, passage_service) -> None:
        self.conn = conn
        self.entity_service = entity_service
        self.passage_service = passage_service

    def lookup(self, query: str, entity_type: str | None = None, limit: int = 5):
        limit = int(limit)
        if limit < 1:
            raise ValueError("limit must be at least 1")

        if entity_type is None:
            entity_type = "people"
        elif entity_type not in ENTITY_TYPES:
            return {"resolved_entity": None, "matches": [], "passages": []}

        search_limit = max(limit, 2)
        matches = self.entity_service.search(query, entity_type=entity_type, limit=search_limit)

        if not matches:
            return {"resolved_entity": None, "matches": [], "passages": []}

        if len(matches) > 1:
            return {"resolved_entity": None, "matches": matches, "passages": []}

        resolved_entity = matches[0]
        passages = self._fetch_passages(
            entity_type=resolved_entity["entity_type"],
            entity_slug=resolved_entity["slug"],
            limit=limit,
        )
        return {"resolved_entity": resolved_entity, "matches": [], "passages": passages}

    def _fetch_passages(self, entity_type: str, entity_slug: str, limit: int):
        rows = self.conn.execute(
            '''
            select reference
            from entity_verse_links
            where entity_type = ? and entity_slug = ?
            order by id
            limit ?
            ''',
            (entity_type, entity_slug, limit),
        ).fetchall()
        return [
            {
                "reference": passage.reference,
                "passage_text": passage.passage_text,
            }
            for row in rows
            for passage in [self.passage_service.lookup(row["reference"])]
        ]
```

- [ ] **Step 4: Re-run the service tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_entity_passage_service.py -q
```

Expected:

```text
all selected tests PASSED
```

- [ ] **Step 5: Commit the new service**

Run:

```bash
git add src/bible_mcp/services/entity_passage_service.py tests/test_entity_passage_service.py
git commit -m "feat: add entity passage lookup service"
```

### Task 3: Wire `get_entity_passages` through MCP and CLI

**Files:**
- Modify: `src/bible_mcp/mcp_server.py`
- Modify: `src/bible_mcp/cli.py`
- Modify: `tests/test_mcp_tools.py`

- [ ] **Step 1: Write the failing MCP handler regressions**

Add a fake service plus handler tests for trimming, invalid limit, and a real-service integration that uses imported default fixtures and seeded verses.

Add to `tests/test_mcp_tools.py`:

```python
class FakeEntityPassageService:
    def __init__(self) -> None:
        self.calls = []

    def lookup(self, query: str, entity_type: str | None = None, limit: int = 5):
        self.calls.append({"query": query, "entity_type": entity_type, "limit": limit})
        return {
            "resolved_entity": {"entity_type": "people", "slug": "abraham", "display_name": "아브라함"},
            "matches": [],
            "passages": [{"reference": "Genesis 12:1", "passage_text": "본문"}],
        }


def test_get_entity_passages_handler_trims_required_query_and_forwards_optional_filters() -> None:
    passage_lookup = FakeEntityPassageService()
    handlers = build_tool_handlers(
        FakeSearchService(),
        FakePassageService(),
        None,
        Mock(),
        FakeEntityService(),
        None,
        passage_lookup,
    )

    result = handlers["get_entity_passages"](
        {"query": " 아브라함 ", "entity_type": " people ", "limit": 2}
    )

    assert passage_lookup.calls == [{"query": "아브라함", "entity_type": "people", "limit": 2}]
    assert result["passages"] == [{"reference": "Genesis 12:1", "passage_text": "본문"}]


def test_get_entity_passages_handler_rejects_invalid_limit() -> None:
    handlers = build_tool_handlers(
        FakeSearchService(),
        FakePassageService(),
        None,
        Mock(),
        FakeEntityService(),
        None,
        FakeEntityPassageService(),
    )

    with pytest.raises(ValueError, match="limit must be at least 1"):
        handlers["get_entity_passages"]({"query": "예루살렘", "limit": 0})
```

Add one real-service integration test using seeded verses plus default fixtures:

```python
def test_get_entity_passages_handler_returns_place_and_event_passages_with_real_services(tmp_path: Path) -> None:
    conn = connect_db(tmp_path / "app.sqlite")
    ensure_schema(conn)
    conn.executemany(
        '''
        insert into verses(translation, book, book_order, chapter, verse, reference, testament, text)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        [
            ("KOR", "Psalms", 19, 122, 2, "Psalms 122:2", "OT", "예루살렘아 우리 발이 네 성문 안에 섰도다"),
            ("KOR", "Matthew", 40, 28, 6, "Matthew 28:6", "NT", "그가 여기 계시지 않고 살아나셨느니라"),
            ("KOR", "Genesis", 1, 12, 1, "Genesis 12:1", "OT", "여호와께서 아브람에게 이르시되"),
            ("KOR", "Genesis", 1, 21, 3, "Genesis 21:3", "OT", "아브라함이 그 아들의 이름을 이삭이라 하였고"),
            ("KOR", "Genesis", 1, 25, 26, "Genesis 25:26", "OT", "후에 나온 아우는"),
            ("KOR", "1 Samuel", 9, 16, 1, "1 Samuel 16:1", "OT", "내가 이미 사울을 버렸거늘"),
            ("KOR", "1 Samuel", 9, 16, 13, "1 Samuel 16:13", "OT", "사무엘이 기름 뿔병을 가져다가"),
            ("KOR", "Matthew", 40, 1, 21, "Matthew 1:21", "NT", "이름을 예수라 하라"),
            ("KOR", "Matthew", 40, 4, 18, "Matthew 4:18", "NT", "갈릴리 해변에 다니시다가"),
            ("KOR", "Matthew", 40, 4, 21, "Matthew 4:21", "NT", "거기서 더 가시다가"),
            ("KOR", "Micah", 33, 5, 2, "Micah 5:2", "OT", "베들레헴 에브라다야"),
            ("KOR", "Matthew", 40, 2, 23, "Matthew 2:23", "NT", "나사렛이란 동네에 가서 사니"),
            ("KOR", "Matthew", 40, 4, 15, "Matthew 4:15", "NT", "이방의 갈릴리여"),
            ("KOR", "Matthew", 40, 3, 13, "Matthew 3:13", "NT", "요단 강에 이르러"),
            ("KOR", "Exodus", 2, 12, 41, "Exodus 12:41", "OT", "여호와의 군대가 다 애굽 땅에서 나왔은즉"),
            ("KOR", "Matthew", 40, 27, 35, "Matthew 27:35", "NT", "그들이 예수를 십자가에 못 박은 후에"),
        ],
    )
    conn.commit()
    import_metadata_fixtures(conn)
    handlers = build_tool_handlers(
        FakeSearchService(),
        PassageService(conn),
        None,
        None,
        EntityService(conn),
        None,
        EntityPassageService(conn, EntityService(conn), PassageService(conn)),
    )

    jerusalem = handlers["get_entity_passages"]({"query": "Jerusalem", "entity_type": "places", "limit": 1})
    resurrection = handlers["get_entity_passages"]({"query": "Resurrection", "entity_type": "events", "limit": 1})

    assert jerusalem["passages"] == [{"reference": "Psalms 122:2", "passage_text": "예루살렘아 우리 발이 네 성문 안에 섰도다"}]
    assert resurrection["passages"] == [{"reference": "Matthew 28:6", "passage_text": "그가 여기 계시지 않고 살아나셨느니라"}]
```

- [ ] **Step 2: Run the new MCP tests to confirm the tool is not wired yet**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_tools.py::test_get_entity_passages_handler_trims_required_query_and_forwards_optional_filters -v
.venv/bin/python -m pytest tests/test_mcp_tools.py::test_get_entity_passages_handler_returns_place_and_event_passages_with_real_services -v
```

Expected:

```text
FAILED with `KeyError: 'get_entity_passages'`
FAILED with `KeyError: 'get_entity_passages'`
```

- [ ] **Step 3: Wire the new service into the handler layer and CLI**

Update `src/bible_mcp/mcp_server.py` to accept an optional `entity_passage_service` in both `build_tool_handlers()` and `create_mcp_server()`, and register a new tool only when the service is present.

Use this structure:

```python
def build_tool_handlers(
    search_service,
    passage_service,
    related_service,
    summarizer,
    entity_service,
    relation_service=None,
    entity_passage_service=None,
):
    def search_bible(payload: dict):
        query = _require_text(payload["query"], "query")
        limit = _require_limit(payload.get("limit", 5))
        results = search_service.search(query, limit=limit)
        return {"results": [_to_payload(result) for result in results]}

    def get_entity_passages(payload: dict):
        query = _require_text(payload["query"], "query")
        entity_type = _optional_text(payload.get("entity_type"))
        limit = _require_limit(payload.get("limit", 5))
        return entity_passage_service.lookup(query, entity_type=entity_type, limit=limit)

    handlers = {
        "search_bible": search_bible,
        "lookup_passage": lookup_passage,
        "expand_context": expand_context,
    }
    if entity_passage_service is not None:
        handlers["get_entity_passages"] = get_entity_passages
    return handlers
```

And in `create_mcp_server()`:

```python
def create_mcp_server(
    search_service,
    passage_service,
    related_service,
    summarizer,
    entity_service,
    relation_service=None,
    entity_passage_service=None,
):
    mcp = FastMCP("bible-mcp")
    handlers = build_tool_handlers(
        search_service,
        passage_service,
        related_service,
        summarizer,
        entity_service,
        relation_service,
        entity_passage_service,
    )
    if "get_entity_passages" in handlers:

        @mcp.tool()
        def get_entity_passages(query: str, entity_type: str | None = None, limit: int = 5):
            return handlers["get_entity_passages"](
                {"query": query, "entity_type": entity_type, "limit": limit}
            )
    return mcp
```

Update `src/bible_mcp/cli.py` to instantiate the new service whenever optional study tools are available:

```python
from bible_mcp.services.entity_passage_service import EntityPassageService

        if _app_db_supports_optional_study_tools(config):
            related_service = RelatedPassageService(conn, embedder, vector_store)
            entity_service = EntityService(conn)
            entity_passage_service = EntityPassageService(conn, entity_service, passage_service)
            summarizer = summarize_passage_text
            relation_service = None
            if _app_db_supports_relation_tools(config):
                relation_service = RelationLookupService(conn, entity_service)
        else:
            related_service = None
            entity_service = None
            entity_passage_service = None
            summarizer = None
            relation_service = None

        create_mcp_server(
            search_service,
            passage_service,
            related_service,
            summarizer,
            entity_service,
            relation_service,
            entity_passage_service,
        ).run()
```

- [ ] **Step 4: Re-run the focused MCP regressions and then the full suite**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_tools.py -q
.venv/bin/python -m pytest tests/test_metadata_loader.py tests/test_metadata_importer.py tests/test_entity_passage_service.py tests/test_mcp_tools.py -q
.venv/bin/python -m pytest -q
```

Expected:

```text
all selected tests PASSED
all selected tests PASSED
all tests PASSED
```

- [ ] **Step 5: Commit the MCP and CLI wiring**

Run:

```bash
git add src/bible_mcp/mcp_server.py src/bible_mcp/cli.py tests/test_mcp_tools.py
git add src/bible_mcp/services/entity_passage_service.py tests/test_entity_passage_service.py
git commit -m "feat: expose entity-linked passages over MCP"
```
