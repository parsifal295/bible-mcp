from __future__ import annotations


class RelatedPassageService:
    def __init__(self, conn, embedder, vector_index) -> None:
        self.conn = conn
        self.embedder = embedder
        self.vector_index = vector_index

    def suggest(self, source_text: str, limit: int = 5):
        query_vector = self.embedder.embed([source_text])[0]
        matches = self.vector_index.search(query_vector, limit=limit)
        results = []
        for chunk_id, score in matches:
            row = self.conn.execute(
                """
                select start_ref, end_ref, text
                from passage_chunks
                where chunk_id = ?
                """,
                (chunk_id,),
            ).fetchone()
            if row is None:
                continue
            results.append(
                {
                    "reference": f"{row['start_ref']}-{row['end_ref']}",
                    "passage_text": row["text"],
                    "score": score,
                }
            )
        return results
