from __future__ import annotations

import re


_RELATION_RULES = (
    (re.compile(r"^(?P<entity>.+?)은 누구 아들인가$"), "father", "father", "incoming"),
    (re.compile(r"^(?P<entity>.+?)의 아버지$"), "father", "father", "incoming"),
    (re.compile(r"^(?P<entity>.+?)의 어머니$"), "mother", "mother", "incoming"),
    (re.compile(r"^(?P<entity>.+?)의 자녀$"), "child", "father", "outgoing"),
    (re.compile(r"^(?P<entity>.+?)의 아들$"), "son", "son", "outgoing"),
    (re.compile(r"^(?P<entity>.+?)의 딸$"), "daughter", "daughter", "outgoing"),
    (re.compile(r"^(?P<entity>.+?)의 형제$"), "brother", "brother", "outgoing"),
    (re.compile(r"^(?P<entity>.+?)의 자매$"), "sister", "sister", "outgoing"),
    (re.compile(r"^(?P<entity>.+?)의 배우자$"), "spouse", "spouse", "outgoing"),
    (re.compile(r"^(?P<entity>.+?)의 제자들?$"), "disciple_of", "disciple_of", "incoming"),
)
_PASSAGE_PATTERN = re.compile(
    r"^(?P<entity>.+?)\s*(대표 구절|관련 구절|연결 구절|등장 구절)$"
)
_EVENT_PATTERN = re.compile(r"^(?P<entity>.+?)\s*사건$")
_PLACE_HINT_TOKENS = ("성", "강", "바다", "산", "광야", "도시")
_PROBE_ENTITY_TYPES = ("places", "events", "people")


class EntityQueryRouter:
    def __init__(
        self,
        entity_service,
        relation_service=None,
        entity_passage_service=None,
    ) -> None:
        self.entity_service = entity_service
        self.relation_service = relation_service
        self.entity_passage_service = entity_passage_service

    def route(self, query: str, limit: int = 5):
        limit = int(limit)
        if limit < 1:
            raise ValueError("limit must be at least 1")

        original_query = query
        normalized_query = str(query).strip()
        if not normalized_query:
            raise ValueError("query cannot be blank")
        parsed = self._parse(normalized_query, original_query, limit)

        if parsed["intent"] == "relations":
            if self.relation_service is None:
                return self._intent_unavailable(parsed, "relations")
            result = self.relation_service.lookup(
                parsed["entity_text"],
                relation_type=parsed.get("_lookup_relation_type", parsed["relation_type"]),
                entity_type=parsed["entity_type"],
                direction=parsed["direction"],
                limit=limit,
            )
        elif parsed["intent"] == "passages":
            if self.entity_passage_service is None:
                return self._intent_unavailable(parsed, "passages")
            result = self.entity_passage_service.lookup(
                parsed["entity_text"],
                entity_type=parsed["entity_type"],
                limit=limit,
            )
        else:
            result = {
                "results": parsed.get("_search_results")
                if parsed.get("_search_results") is not None
                else self.entity_service.search(
                    parsed["entity_text"],
                    entity_type=parsed["entity_type"],
                    limit=limit,
                )
            }

        return {
            "intent": parsed["intent"],
            "parsed": {
                "original_query": original_query,
                "normalized_query": normalized_query,
                "entity_text": parsed["entity_text"],
                "entity_type": parsed["entity_type"],
                "relation_type": parsed["relation_type"],
                "direction": parsed["direction"],
                "target_tool": parsed["target_tool"],
            },
            "result": result,
            "error": None,
        }

    def _parse(self, normalized_query: str, original_query: str, limit: int):
        relation = self._parse_relation(normalized_query)
        if relation is not None:
            relation["original_query"] = original_query
            return relation

        passage = self._parse_passage(normalized_query, limit)
        if passage is not None:
            passage["original_query"] = original_query
            return passage

        event_match = _EVENT_PATTERN.match(normalized_query)
        if event_match is not None:
            entity_text, search_results = self._resolve_event_query_text(
                normalized_query,
                limit,
            )
            return {
                "intent": "entity_search",
                "original_query": original_query,
                "normalized_query": normalized_query,
                "entity_text": entity_text,
                "entity_type": "events",
                "relation_type": None,
                "direction": None,
                "target_tool": "search_entities",
                "_search_results": search_results,
            }

        entity_text = normalized_query
        entity_type, search_results = self._infer_entity_type(
            entity_text,
            normalized_query,
            "entity_search",
            limit,
        )

        return {
            "intent": "entity_search",
            "original_query": original_query,
            "normalized_query": normalized_query,
            "entity_text": entity_text,
            "entity_type": entity_type,
            "relation_type": None,
            "direction": None,
            "target_tool": "search_entities",
            "_search_results": search_results,
        }

    def _parse_relation(self, normalized_query: str):
        for pattern, relation_type, lookup_relation_type, direction in _RELATION_RULES:
            match = pattern.match(normalized_query)
            if match is None:
                continue
            entity_text = match.group("entity").strip()
            return {
                "intent": "relations",
                "normalized_query": normalized_query,
                "entity_text": entity_text,
                "entity_type": "people",
                "relation_type": relation_type,
                "direction": direction,
                "target_tool": "get_entity_relations",
                "_lookup_relation_type": lookup_relation_type,
            }
        return None

    def _parse_passage(self, normalized_query: str, limit: int):
        match = _PASSAGE_PATTERN.match(normalized_query)
        if match is None:
            return None

        entity_text = match.group("entity").strip()
        if _EVENT_PATTERN.match(entity_text) is not None:
            entity_text, _search_results = self._resolve_event_query_text(
                entity_text,
                limit,
            )
            entity_type = "events"
        else:
            entity_type, _search_results = self._infer_entity_type(
                entity_text,
                normalized_query,
                "passages",
                limit,
            )
        return {
            "intent": "passages",
            "normalized_query": normalized_query,
            "entity_text": entity_text,
            "entity_type": entity_type,
            "relation_type": None,
            "direction": None,
            "target_tool": "get_entity_passages",
        }

    def _infer_entity_type(
        self,
        entity_text: str,
        normalized_query: str,
        intent: str,
        limit: int,
    ) -> tuple[str | None, list[dict] | None]:
        if intent == "relations":
            return "people", None

        if "사건" in normalized_query:
            return "events", None

        if self._looks_like_place(entity_text):
            return "places", None

        for entity_type in _PROBE_ENTITY_TYPES:
            matches = self.entity_service.search(
                entity_text,
                entity_type=entity_type,
                limit=limit,
            )
            if matches:
                return entity_type, matches
        return None, None

    def _looks_like_place(self, entity_text: str) -> bool:
        return any(entity_text.endswith(token) for token in _PLACE_HINT_TOKENS)

    def _resolve_event_query_text(
        self,
        event_query_text: str,
        limit: int,
    ) -> tuple[str, list[dict]]:
        direct_matches = self.entity_service.search(
            event_query_text,
            entity_type="events",
            limit=limit,
        )
        if direct_matches:
            return event_query_text, direct_matches

        match = _EVENT_PATTERN.match(event_query_text)
        if match is None:
            return event_query_text, []

        stripped_text = match.group("entity").strip()
        stripped_matches = self.entity_service.search(
            stripped_text,
            entity_type="events",
            limit=limit,
        )
        return stripped_text, stripped_matches

    def _intent_unavailable(self, parsed: dict, intent: str):
        return {
            "intent": parsed["intent"],
            "parsed": {
                "original_query": parsed["original_query"],
                "normalized_query": parsed["normalized_query"],
                "entity_text": parsed["entity_text"],
                "entity_type": parsed["entity_type"],
                "relation_type": parsed["relation_type"],
                "direction": parsed["direction"],
                "target_tool": parsed["target_tool"],
            },
            "result": None,
            "error": {
                "code": "intent_unavailable",
                "message": f"{intent} intent is unavailable in this runtime",
            },
        }
