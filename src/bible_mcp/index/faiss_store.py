from __future__ import annotations

import json
from pathlib import Path

import numpy as np

try:  # pragma: no cover - native dependency is optional in this environment
    import faiss
except ImportError:  # pragma: no cover - exercised indirectly via fallback behavior
    faiss = None


class FaissChunkIndex:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.mapping_path = path.with_suffix(".json")
        self.id_map: list[str] = []
        self.index = None
        self._matrix: np.ndarray | None = None

    def build(self, embeddings: list[tuple[str, list[float]]]) -> None:
        self.id_map = [chunk_id for chunk_id, _ in embeddings]
        matrix = np.array([vector for _, vector in embeddings], dtype="float32")

        if matrix.size == 0:
            self._matrix = matrix.reshape(0, 0)
            self.index = None
            self.path.write_text(
                json.dumps({"dimension": 0, "vectors": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            self.mapping_path.write_text(json.dumps(self.id_map, ensure_ascii=False), encoding="utf-8")
            return

        if faiss is not None:
            self.index = faiss.IndexFlatIP(matrix.shape[1])
            self.index.add(matrix)
            faiss.write_index(self.index, str(self.path))
            self._matrix = None
        else:
            self._matrix = matrix
            self.path.write_text(
                json.dumps(
                    {
                        "dimension": matrix.shape[1],
                        "vectors": matrix.tolist(),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

        self.mapping_path.write_text(
            json.dumps(self.id_map, ensure_ascii=False), encoding="utf-8"
        )

    def load(self) -> None:
        self.id_map = json.loads(self.mapping_path.read_text(encoding="utf-8"))

        if faiss is not None:
            try:
                self.index = faiss.read_index(str(self.path))
                self._matrix = None
                return
            except RuntimeError:
                # Fall through to the JSON fallback written by environments without faiss.
                pass

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self._matrix = np.array(payload["vectors"], dtype="float32")
        self.index = None

    def search(self, query_vector: list[float], limit: int = 5) -> list[tuple[str, float]]:
        if self.index is None and self._matrix is None:
            self.load()

        query = np.array([query_vector], dtype="float32")

        if self.index is not None:
            scores, indexes = self.index.search(query, limit)
            return [
                (self.id_map[index], float(scores[0][offset]))
                for offset, index in enumerate(indexes[0])
                if index >= 0
            ]

        if self._matrix is None or self._matrix.size == 0:
            return []

        scores = self._matrix @ query[0]
        top_indexes = np.argsort(-scores)[:limit]
        return [(self.id_map[index], float(scores[index])) for index in top_indexes]
