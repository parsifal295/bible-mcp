from __future__ import annotations

from bible_mcp.domain.metadata import ENTITY_TYPES


class EntityPassageService:
    def __init__(self, conn, entity_service, passage_service) -> None:
        self.conn = conn
        self.entity_service = entity_service
        self.passage_service = passage_service
        self._available_tables = self._load_available_tables()

    def _load_available_tables(self) -> set[str]:
        rows = self.conn.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()
        return {row["name"] for row in rows}

    def _has_table(self, table_name: str) -> bool:
        return table_name in self._available_tables

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
        if not self._has_table("entity_verse_links"):
            return {
                "resolved_entity": resolved_entity,
                "matches": [],
                "passages": [],
            }
        passages = self._fetch_passages(
            entity_type=resolved_entity["entity_type"],
            entity_slug=resolved_entity["slug"],
            limit=limit,
        )
        return {
            "resolved_entity": resolved_entity,
            "matches": [],
            "passages": passages,
        }

    def _fetch_passages(self, entity_type: str, entity_slug: str, limit: int):
        rows = self.conn.execute(
            """
            select reference
            from entity_verse_links
            where entity_type = ? and entity_slug = ?
            order by id
            limit ?
            """,
            (entity_type, entity_slug, limit),
        ).fetchall()

        passages = []
        for row in rows:
            passage = self.passage_service.lookup(row["reference"])
            passages.append(
                {
                    "reference": passage.reference,
                    "passage_text": passage.passage_text,
                }
            )
        return passages
