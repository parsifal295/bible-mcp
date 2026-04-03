from pathlib import Path

from pydantic import BaseModel, Field


class SourceBibleConfig(BaseModel):
    path: Path
    table: str = "verses"


class EmbeddingConfig(BaseModel):
    model_name: str = "intfloat/multilingual-e5-small"
    batch_size: int = 16


class TheographicConfig(BaseModel):
    repo: str = "robertrouse/theographic-bible-metadata"
    ref: str = "master"
    vendor_dir: Path = Path("data/vendor/theographic")
    link_limit: int = 20


class AppConfig(BaseModel):
    source: SourceBibleConfig
    app_db_path: Path
    faiss_index_path: Path
    embeddings: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    theographic: TheographicConfig = Field(default_factory=TheographicConfig)
