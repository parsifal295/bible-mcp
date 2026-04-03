import json
from pathlib import Path
import sqlite3

import pytest

from bible_mcp.db.schema import ensure_schema
from bible_mcp.index.embeddings import index_chunk_embeddings
from bible_mcp.index.faiss_store import FaissChunkIndex


class FakeEmbedder:
    model_name = "fake"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(index + 1), float(index + 2)] for index, _ in enumerate(texts)]


class FakeVectorStore:
    def __init__(self) -> None:
        self.embeddings: list[tuple[str, list[float]]] | None = None

    def build(self, embeddings: list[tuple[str, list[float]]]) -> None:
        self.embeddings = embeddings


class FailingVectorStore:
    def build(self, embeddings: list[tuple[str, list[float]]]) -> None:
        raise RuntimeError("vector store failed")


class ShortEmbedder:
    model_name = "short"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0]] if texts else []


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


def test_faiss_index_rejects_empty_embeddings(tmp_path: Path) -> None:
    store = FaissChunkIndex(tmp_path / "chunks.faiss")

    with pytest.raises(ValueError, match="empty"):
        store.build([])


def test_faiss_index_detects_stale_mapping_cardinality(tmp_path: Path) -> None:
    path = tmp_path / "chunks.faiss"
    store = FaissChunkIndex(path)
    store.build(
        [
            ("chunk-a", [1.0, 0.0]),
            ("chunk-b", [0.0, 1.0]),
        ]
    )
    store.mapping_path.write_text('["chunk-a"]', encoding="utf-8")

    reloaded = FaissChunkIndex(path)

    with pytest.raises(ValueError, match="mapping"):
        reloaded.search([1.0, 0.0], limit=1)


def test_faiss_index_rejects_same_length_wrong_mapping(tmp_path: Path) -> None:
    path = tmp_path / "chunks.faiss"
    store = FaissChunkIndex(path)
    store.build(
        [
            ("chunk-a", [1.0, 0.0]),
            ("chunk-b", [0.0, 1.0]),
        ]
    )
    store.mapping_path.write_text(
        json.dumps(["chunk-x", "chunk-y"], ensure_ascii=False),
        encoding="utf-8",
    )

    reloaded = FaissChunkIndex(path)

    with pytest.raises(ValueError, match="integrity"):
        reloaded.search([1.0, 0.0], limit=1)


def test_faiss_index_cleans_up_if_sidecar_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "chunks.faiss"
    store = FaissChunkIndex(path)
    original_write_text = Path.write_text

    def failing_write_text(self: Path, *args, **kwargs):
        if self.name.endswith(".json.tmp") or self.name.endswith(".meta.json.tmp"):
            raise RuntimeError("sidecar write failed")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    with pytest.raises(RuntimeError, match="sidecar write failed"):
        store.build(
            [
                ("chunk-a", [1.0, 0.0]),
                ("chunk-b", [0.0, 1.0]),
            ]
        )

    assert not path.exists()
    assert not store.mapping_path.exists()
    assert not store.integrity_path.exists()


def test_faiss_index_restores_previous_artifacts_if_final_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "chunks.faiss"
    store = FaissChunkIndex(path)
    store.build(
        [
            ("chunk-a", [1.0, 0.0]),
            ("chunk-b", [0.0, 1.0]),
        ]
    )

    original_replace = Path.replace

    def failing_replace(self: Path, target: Path):
        if self == path.with_name("chunks.faiss.tmp") and target == path:
            raise RuntimeError("final publish failed")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", failing_replace)

    with pytest.raises(RuntimeError, match="final publish failed"):
        store.build(
            [
                ("chunk-c", [0.0, 1.0]),
                ("chunk-d", [1.0, 0.0]),
            ]
        )

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


def test_index_chunk_embeddings_rolls_back_metadata_when_vector_store_fails() -> None:
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

    with pytest.raises(RuntimeError, match="vector store failed"):
        index_chunk_embeddings(conn, FakeEmbedder(), FailingVectorStore())

    assert conn.execute("select count(*) from chunk_embeddings").fetchone()[0] == 0


def test_index_chunk_embeddings_rejects_vector_count_mismatch() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    conn.executemany(
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
        [
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
            (
                "chunk-b",
                "Genesis 1:2",
                "Genesis 1:2",
                "Genesis",
                "1",
                "땅이 혼돈하고 공허하며",
                4,
                "verse_window",
            ),
        ],
    )

    with pytest.raises(ValueError, match="embedding"):
        index_chunk_embeddings(conn, ShortEmbedder(), FakeVectorStore())

    assert conn.execute("select count(*) from chunk_embeddings").fetchone()[0] == 0
