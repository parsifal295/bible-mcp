from abc import ABC, abstractmethod
from datetime import UTC, datetime
import sqlite3


class Embedder(ABC):
    model_name: str

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class SentenceTransformerEmbedder(Embedder):
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on optional dependency
            raise RuntimeError(
                "sentence-transformers is required for SentenceTransformerEmbedder"
            ) from exc
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]


def index_chunk_embeddings(
    conn: sqlite3.Connection,
    embedder: Embedder,
    vector_store,
    embedding_version: str = "v1",
) -> None:
    rows = conn.execute(
        "select chunk_id, text from passage_chunks order by id"
    ).fetchall()
    texts = [row["text"] for row in rows]
    embeddings = list(zip([row["chunk_id"] for row in rows], embedder.embed(texts)))

    with conn:
        conn.execute("delete from chunk_embeddings")
        for chunk_id, _vector in embeddings:
            conn.execute(
                """
                insert into chunk_embeddings(chunk_id, model_name, embedding_version, updated_at)
                values (?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    embedder.model_name,
                    embedding_version,
                    datetime.now(UTC).isoformat(),
                ),
            )
    vector_store.build(embeddings)
