from __future__ import annotations


_ENTITY_SEARCH_TYPES = {
    "people": {"table": "people", "description_sql": "description"},
    "places": {"table": "places", "description_sql": "null"},
    "events": {"table": "events", "description_sql": "description"},
}
_ENTITY_TYPE_ALIASES = {
    "person": "people",
    "people": "people",
    "place": "places",
    "places": "places",
    "event": "events",
    "events": "events",
}
_PLACE_QUERY_SUFFIXES = (" 위치", " 지도", " 좌표", " 위경도")

_MATCH_PRIORITY = {"display_name": 0, "alias": 1, "slug": 2}
_MATCH_ORDER = ("display_name", "alias", "slug")


class EntityService:
    def __init__(self, conn) -> None:
        self.conn = conn
        self._available_tables = self._load_available_tables()

    def _load_available_tables(self) -> set[str]:
        rows = self.conn.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()
        return {row["name"] for row in rows}

    def _has_table(self, table_name: str) -> bool:
        return table_name in self._available_tables

    def _entity_types_for_search(self, entity_type: str | None) -> tuple[str, ...]:
        if entity_type is None:
            return ("people",)
        normalized_entity_type = str(entity_type).strip().lower()
        canonical_entity_type = _ENTITY_TYPE_ALIASES.get(normalized_entity_type)
        if canonical_entity_type not in _ENTITY_SEARCH_TYPES:
            return ()
        return (canonical_entity_type,)

    def _query_variants(self, query: str, entity_type: str) -> tuple[str, ...]:
        variants: list[str] = []

        def add(candidate: str) -> None:
            normalized = " ".join(candidate.split())
            if not normalized:
                return
            if normalized not in variants:
                variants.append(normalized)
            compact = normalized.replace(" ", "")
            if compact and compact not in variants:
                variants.append(compact)

        add(query)

        if entity_type == "places":
            for suffix in _PLACE_QUERY_SUFFIXES:
                if not query.endswith(suffix):
                    continue
                stripped = query[: -len(suffix)].strip()
                if stripped:
                    add(stripped)

        return tuple(variants)

    def _optional_place_columns(self, entity_type: str, table_alias: str = "") -> str:
        if entity_type != "places":
            return ""
        prefix = f"{table_alias}." if table_alias else ""
        return f", {prefix}latitude as latitude, {prefix}longitude as longitude"

    def _google_maps_url(self, latitude: float | None, longitude: float | None) -> str | None:
        if latitude is None or longitude is None:
            return None
        return f"https://www.google.com/maps?q={latitude},{longitude}"

    def _candidate_from_row(self, row, matched_by: str) -> dict:
        candidate = {
            "entity_type": row["entity_type"],
            "slug": row["slug"],
            "display_name": row["display_name"],
            "description": row["description"],
            "matched_by": matched_by,
            "_rank": _MATCH_PRIORITY[matched_by],
        }
        if row["entity_type"] == "places":
            latitude = row["latitude"]
            longitude = row["longitude"]
            candidate["latitude"] = latitude
            candidate["longitude"] = longitude
            candidate["google_maps_url"] = self._google_maps_url(latitude, longitude)
        return candidate

    def _match_sql(self, entity_type: str, matched_by: str) -> str:
        config = _ENTITY_SEARCH_TYPES[entity_type]
        table = config["table"]
        description_sql = config["description_sql"]
        optional_place_columns = self._optional_place_columns(entity_type)

        if matched_by == "display_name":
            return f"""
                select '{entity_type}' as entity_type, slug, display_name, {description_sql} as description{optional_place_columns}
                from {table}
                where display_name = ?
                order by display_name, slug
            """

        if matched_by == "alias":
            optional_place_columns = self._optional_place_columns(entity_type, table_alias="p")
            return f"""
                select '{entity_type}' as entity_type, p.slug, p.display_name, {description_sql} as description{optional_place_columns}
                from {table} p
                join entity_aliases a
                  on a.entity_type = '{entity_type}' and a.entity_slug = p.slug
                where a.alias = ?
                order by p.display_name, p.slug
            """

        if matched_by == "slug":
            return f"""
                select '{entity_type}' as entity_type, slug, display_name, {description_sql} as description{optional_place_columns}
                from {table}
                where slug = ?
                order by display_name, slug
            """

        raise ValueError(f"unsupported match kind: {matched_by}")

    def search(self, query: str, entity_type: str | None = None, limit: int = 5):
        entity_types = self._entity_types_for_search(entity_type)
        if not entity_types:
            return []

        limit = int(limit)
        if limit < 1:
            raise ValueError("limit must be at least 1")

        candidates: dict[tuple[str, str], dict] = {}

        for current_entity_type in entity_types:
            config = _ENTITY_SEARCH_TYPES[current_entity_type]
            if not self._has_table(config["table"]):
                continue
            query_variants = self._query_variants(query, current_entity_type)
            for matched_by in _MATCH_ORDER:
                if matched_by == "alias" and not self._has_table("entity_aliases"):
                    continue
                sql = self._match_sql(current_entity_type, matched_by)
                for query_variant in query_variants:
                    for row in self.conn.execute(sql, (query_variant,)).fetchall():
                        candidate = self._candidate_from_row(row, matched_by)
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
