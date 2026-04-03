from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np


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
        self.index = faiss.IndexFlatIP(matrix.shape[1])
        self.index.add(matrix)
        faiss.write_index(self.index, str(self.path))

        self.mapping_path.write_text(
            json.dumps(self.id_map, ensure_ascii=False), encoding="utf-8"
        )

    def load(self) -> None:
        self.id_map = json.loads(self.mapping_path.read_text(encoding="utf-8"))
        self.index = faiss.read_index(str(self.path))

    def search(self, query_vector: list[float], limit: int = 5) -> list[tuple[str, float]]:
        if self.index is None:
            self.load()

        query = np.array([query_vector], dtype="float32")
        scores, indexes = self.index.search(query, limit)
        return [
            (self.id_map[index], float(scores[0][offset]))
            for offset, index in enumerate(indexes[0])
            if index >= 0
        ]
