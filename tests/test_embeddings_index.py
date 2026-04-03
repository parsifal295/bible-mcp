from pathlib import Path
import sqlite3

from bible_mcp.index.faiss_store import FaissChunkIndex
from bible_mcp.index.embeddings import index_chunk_embeddings
from bible_mcp.db.schema import ensure_schema


class FakeEmbedder:
    model_name = "fake"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(index + 1), float(index + 2)] for index, _ in enumerate(texts)]


class FakeVectorStore:
    def __init__(self) -> None:
        self.embeddings: list[tuple[str, list[float]]] | None = None

    def build(self, embeddings: list[tuple[str, list[float]]]) -> None:
        self.embeddings = embeddings


def test_faiss_index_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "chunks.faiss"
    store = FaissChunkIndex(path)
    embeddings = [
        ("chunk-a", [1.0, 0.0]),
        ("chunk-b", [0.0, 1.0]),
    ]
    store.build(embeddings)

    reloaded = FaissChunkIndex(path)
    matches = reloaded.search([1.0, 0.0], limit=1)

    assert matches[0][0] == "chunk-a"


def test_index_chunk_embeddings_writes_metadata_and_vectors() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    conn.execute(
        """
        insert into passage_chunks(
            chunk_id,
            start_ref,
            end_ref,
            book,
            chapter_range,
            text,
            token_count,
            chunk_strategy
        )
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "chunk-a",
            "Genesis 1:1",
            "Genesis 1:1",
            "Genesis",
            "1",
            "태초에 하나님이 천지를 창조하시니라",
            5,
            "verse_window",
        ),
    )

    embedder = FakeEmbedder()
    vector_store = FakeVectorStore()

    index_chunk_embeddings(conn, embedder, vector_store)

    row = conn.execute(
        "select chunk_id, model_name, embedding_version, updated_at from chunk_embeddings"
    ).fetchone()

    assert row["chunk_id"] == "chunk-a"
    assert row["model_name"] == "fake"
    assert row["embedding_version"] == "v1"
    assert row["updated_at"]
    assert vector_store.embeddings == [("chunk-a", [1.0, 2.0])]
