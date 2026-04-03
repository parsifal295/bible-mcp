from __future__ import annotations


class EntityService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def search(self, query: str, entity_type: str | None = None, limit: int = 5):
        if entity_type is not None and entity_type != "people":
            return []

        limit = int(limit)
        if limit < 1:
            raise ValueError("limit must be at least 1")

        match_priority = {"display_name": 0, "alias": 1, "slug": 2}
        candidates: dict[tuple[str, str], dict] = {}

        match_queries = (
            (
                "display_name",
                """
                select 'people' as entity_type, slug, display_name, description
                from people
                where display_name = ?
                order by display_name, slug
                """,
            ),
            (
                "alias",
                """
                select 'people' as entity_type, p.slug, p.display_name, p.description
                from people p
                join entity_aliases a
                  on a.entity_type = 'people' and a.entity_slug = p.slug
                where a.alias = ?
                order by p.display_name, p.slug
                """,
            ),
            (
                "slug",
                """
                select 'people' as entity_type, slug, display_name, description
                from people
                where slug = ?
                order by display_name, slug
                """,
            ),
        )

        for matched_by, sql in match_queries:
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
            key=lambda candidate: (
                candidate["_rank"],
                candidate["display_name"],
                candidate["slug"],
            ),
        )
        return [
            {key: value for key, value in candidate.items() if key != "_rank"}
            for candidate in ordered[:limit]
        ]
