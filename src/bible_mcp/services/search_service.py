from __future__ import annotations

from dataclasses import dataclass
import re

from bible_mcp.query.context import expand_chunk_context
from bible_mcp.query.hybrid import fuse_scores


@dataclass
class SearchResult:
    reference: str
    passage_text: str
    score: float
    match_reasons: list[str]
    related_entities: list[str]


def _normalize_query(query: str) -> str | None:
    tokens = re.findall(r"\w+", query, flags=re.UNICODE)
    if not tokens:
        return None
    return " ".join(f'"{token.replace("\"", "\"\"")}"' for token in tokens)


class SearchService:
    def __init__(self, conn, embedder, vector_index) -> None:
        self.conn = conn
        self.embedder = embedder
        self.vector_index = vector_index

    def _chunk_for_id(self, chunk_id: str):
        return self.conn.execute(
            """
            select chunk_id, start_ref, end_ref, text
            from passage_chunks
            where chunk_id = ?
            """,
            (chunk_id,),
        ).fetchone()

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        normalized_query = _normalize_query(query)
        semantic_query = self.embedder.embed([query])[0]
        semantic_hits = {
            chunk_id: score for chunk_id, score in self.vector_index.search(semantic_query, limit=limit)
        }

        candidates: dict[str, dict[str, object]] = {}

        if normalized_query is not None:
            for rank, chunk in enumerate(
                self.conn.execute(
                    """
                    select pc.chunk_id, pc.start_ref, pc.end_ref, pc.text
                    from passage_chunks_fts
                    join passage_chunks pc on pc.id = passage_chunks_fts.rowid
                    where passage_chunks_fts match ?
                    order by bm25(passage_chunks_fts), pc.id
                    limit ?
                    """,
                    (normalized_query, limit),
                ).fetchall()
            ):
                candidates[chunk["chunk_id"]] = {
                    "chunk": chunk,
                    "keyword_score": 1.0 - (rank * 0.05),
                    "keyword": True,
                }

        for chunk_id in semantic_hits:
            if chunk_id in candidates:
                continue
            chunk = self._chunk_for_id(chunk_id)
            if chunk is None:
                continue
            candidates[chunk_id] = {
                "chunk": chunk,
                "keyword_score": 0.0,
                "keyword": False,
            }

        results: list[SearchResult] = []
        for chunk_id, entry in candidates.items():
            chunk = entry["chunk"]
            semantic_score = semantic_hits.get(chunk_id, 0.0)
            keyword_score = float(entry["keyword_score"])
            match_reasons: list[str] = []
            if entry["keyword"]:
                match_reasons.append("keyword")
            if semantic_score:
                match_reasons.append("semantic")

            context_rows = expand_chunk_context(
                self.conn,
                chunk["start_ref"],
                chunk["end_ref"],
                window=0,
            )
            results.append(
                SearchResult(
                    reference=f"{chunk['start_ref']}-{chunk['end_ref']}",
                    passage_text=" ".join(row["text"] for row in context_rows),
                    score=fuse_scores(keyword_score=keyword_score, semantic_score=semantic_score),
                    match_reasons=match_reasons,
                    related_entities=[],
                )
            )

        results.sort(key=lambda result: result.score, reverse=True)
        return results[:limit]
