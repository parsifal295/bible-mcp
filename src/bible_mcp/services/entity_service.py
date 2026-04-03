from __future__ import annotations


class EntityService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def search(self, query: str):
        rows = self.conn.execute(
            """
            select distinct p.slug, p.display_name, p.description
            from people p
            left join entity_aliases a
              on a.entity_type = 'people' and a.entity_slug = p.slug
            where p.display_name = ? or a.alias = ?
            order by p.display_name
            """,
            (query, query),
        ).fetchall()
        return [dict(row) for row in rows]
