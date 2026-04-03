from __future__ import annotations

import hashlib
import json
from pathlib import Path

import faiss
import numpy as np


class FaissChunkIndex:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.mapping_path = path.with_suffix(".json")
        self.integrity_path = path.with_suffix(".meta.json")
        self.id_map: list[str] = []
        self.index = None

    @staticmethod
    def _serialize_id_map(id_map: list[str]) -> str:
        return json.dumps(id_map, ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def _mapping_digest(cls, id_map: list[str]) -> str:
        payload = cls._serialize_id_map(id_map).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _temp_path(path: Path) -> Path:
        return path.with_name(f"{path.name}.tmp")

    @staticmethod
    def _cleanup_paths(*paths: Path) -> None:
        for path in paths:
            path.unlink(missing_ok=True)

    @staticmethod
    def _backup_path(path: Path) -> Path:
        return path.with_name(f"{path.name}.bak")

    def _restore_backups(self, backups: dict[Path, Path]) -> None:
        for live_path, backup_path in backups.items():
            live_path.unlink(missing_ok=True)
            backup_path.replace(live_path)

    def _clear_partial_publication(self) -> None:
        self._cleanup_paths(self.path, self.mapping_path, self.integrity_path)

    def build(self, embeddings: list[tuple[str, list[float]]]) -> None:
        if not embeddings:
            raise ValueError("cannot build a FAISS index from empty embeddings")
        self.id_map = [chunk_id for chunk_id, _ in embeddings]
        matrix = np.array([vector for _, vector in embeddings], dtype="float32")
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)

        mapping_text = self._serialize_id_map(self.id_map)
        integrity_text = json.dumps(
            {
                "mapping_sha256": self._mapping_digest(self.id_map),
                "count": len(self.id_map),
            },
            ensure_ascii=False,
        )

        index_tmp = self._temp_path(self.path)
        mapping_tmp = self._temp_path(self.mapping_path)
        integrity_tmp = self._temp_path(self.integrity_path)
        backups: dict[Path, Path] = {}

        try:
            faiss.write_index(index, str(index_tmp))
            mapping_tmp.write_text(mapping_text, encoding="utf-8")
            integrity_tmp.write_text(integrity_text, encoding="utf-8")
            for live_path in (self.path, self.mapping_path, self.integrity_path):
                backup_path = self._backup_path(live_path)
                if live_path.exists():
                    self._cleanup_paths(backup_path)
                    live_path.replace(backup_path)
                    backups[live_path] = backup_path

            mapping_tmp.replace(self.mapping_path)
            integrity_tmp.replace(self.integrity_path)
            index_tmp.replace(self.path)
        except Exception:
            if backups:
                self._restore_backups(backups)
            else:
                self._clear_partial_publication()
            self._cleanup_paths(index_tmp, mapping_tmp, integrity_tmp)
            self._cleanup_paths(*backups.values())
            raise
        else:
            self._cleanup_paths(*backups.values())
        self.index = index

    def load(self) -> None:
        id_map = json.loads(self.mapping_path.read_text(encoding="utf-8"))
        integrity = json.loads(self.integrity_path.read_text(encoding="utf-8"))
        if integrity.get("count") != len(id_map):
            raise ValueError("FAISS mapping integrity mismatch: count does not match")
        if integrity.get("mapping_sha256") != self._mapping_digest(id_map):
            raise ValueError("FAISS mapping integrity mismatch: digest does not match")

        index = faiss.read_index(str(self.path))
        if index.ntotal != len(id_map):
            raise ValueError(
                "FAISS index and mapping cardinality mismatch: "
                f"{index.ntotal} vectors for {len(id_map)} ids"
            )
        self.id_map = id_map
        self.index = index

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
