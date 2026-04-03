from __future__ import annotations


class RelationLookupService:
    def __init__(self, conn, entity_service) -> None:
        self.conn = conn
        self.entity_service = entity_service

    def lookup(
        self,
        query: str,
        relation_type: str | None = None,
        entity_type: str | None = None,
        direction: str = "outgoing",
        limit: int = 5,
    ):
        limit = int(limit)
        if limit < 1:
            raise ValueError("limit must be at least 1")

        if direction not in {"outgoing", "incoming"}:
            raise ValueError("direction must be 'outgoing' or 'incoming'")

        if entity_type is None:
            entity_type = "people"
        elif entity_type != "people":
            return {"resolved_entity": None, "matches": [], "relations": []}

        search_limit = max(limit, 2)
        matches = self.entity_service.search(query, entity_type=entity_type, limit=search_limit)

        if not matches:
            return {"resolved_entity": None, "matches": [], "relations": []}

        if len(matches) > 1:
            return {"resolved_entity": None, "matches": matches, "relations": []}

        resolved_entity = matches[0]
        relations = self._fetch_relations(
            entity_slug=resolved_entity["slug"],
            relation_type=relation_type,
            direction=direction,
            limit=limit,
        )
        return {
            "resolved_entity": resolved_entity,
            "matches": [],
            "relations": relations,
        }

    def _fetch_relations(
        self,
        entity_slug: str,
        relation_type: str | None,
        direction: str,
        limit: int,
    ):
        relation_filter = ""
        params: list[object] = [entity_slug]

        if relation_type is not None:
            relation_filter = "and er.relation_type = ?"
            params.append(relation_type)

        if direction == "outgoing":
            sql = f"""
                select
                    distinct
                    er.relation_type,
                    p.slug,
                    p.display_name,
                    p.description
                from entity_relationships er
                join people p
                  on p.slug = er.target_slug
                 and er.target_type = 'people'
                where er.source_type = 'people'
                  and er.source_slug = ?
                  {relation_filter}
                order by er.relation_type, p.display_name, p.slug
                limit ?
            """
        else:
            sql = f"""
                select
                    distinct
                    er.relation_type,
                    p.slug,
                    p.display_name,
                    p.description
                from entity_relationships er
                join people p
                  on p.slug = er.source_slug
                 and er.source_type = 'people'
                where er.target_type = 'people'
                  and er.target_slug = ?
                  {relation_filter}
                order by er.relation_type, p.display_name, p.slug
                limit ?
            """

        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [
            {
                "relation_type": row["relation_type"],
                "entity_type": "people",
                "slug": row["slug"],
                "display_name": row["display_name"],
                "description": row["description"],
            }
            for row in rows
        ]
