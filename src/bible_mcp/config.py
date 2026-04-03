from pathlib import Path

from pydantic import BaseModel, Field


class SourceBibleConfig(BaseModel):
    path: Path
    table: str = "verses"


class EmbeddingConfig(BaseModel):
    model_name: str = "intfloat/multilingual-e5-small"
    batch_size: int = 16


class AppConfig(BaseModel):
    source: SourceBibleConfig
    app_db_path: Path
    faiss_index_path: Path
    embeddings: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
