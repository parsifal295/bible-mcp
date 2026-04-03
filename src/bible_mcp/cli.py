import os
from pathlib import Path

import typer

from bible_mcp.config import AppConfig, SourceBibleConfig
from bible_mcp.db.connection import connect_db
from bible_mcp.db.schema import ensure_schema
from bible_mcp.index.embeddings import SentenceTransformerEmbedder, index_chunk_embeddings
from bible_mcp.index.faiss_store import FaissChunkIndex
from bible_mcp.index.fts import rebuild_fts_indexes
from bible_mcp.ingest.chunker import build_chunks
from bible_mcp.ingest.importer import import_verses
from bible_mcp.ingest.source_db import SourceSchemaError, validate_source_database
from bible_mcp.mcp_server import create_mcp_server
from bible_mcp.services.passage_service import PassageService
from bible_mcp.services.search_service import SearchService

app = typer.Typer(help="Korean Bible MCP server")


def load_config() -> AppConfig:
    source_path = Path(os.environ["BIBLE_SOURCE_DB"])
    source_table = os.environ.get("BIBLE_SOURCE_TABLE", "verses")
    app_db_path = Path(os.environ.get("BIBLE_APP_DB", "data/app.sqlite"))
    faiss_index_path = Path(os.environ.get("BIBLE_FAISS_INDEX", "data/chunks.faiss"))
    app_db_path.parent.mkdir(parents=True, exist_ok=True)
    faiss_index_path.parent.mkdir(parents=True, exist_ok=True)
    return AppConfig(
        source=SourceBibleConfig(path=source_path, table=source_table),
        app_db_path=app_db_path,
        faiss_index_path=faiss_index_path,
    )


@app.command()
def index() -> None:
    config = load_config()
    validate_source_database(config.source)
    conn = connect_db(config.app_db_path)
    ensure_schema(conn)
    import_verses(config, conn)
    build_chunks(conn)
    rebuild_fts_indexes(conn)
    embedder = SentenceTransformerEmbedder(config.embeddings.model_name)
    vector_store = FaissChunkIndex(config.faiss_index_path)
    index_chunk_embeddings(conn, embedder, vector_store)
    typer.echo("Index build complete")


@app.command()
def serve() -> None:
    config = load_config()
    conn = connect_db(config.app_db_path)
    embedder = SentenceTransformerEmbedder(config.embeddings.model_name)
    vector_store = FaissChunkIndex(config.faiss_index_path)
    search_service = SearchService(conn, embedder, vector_store)
    passage_service = PassageService(conn)
    create_mcp_server(search_service, passage_service, None, None, None).run()


@app.command()
def doctor() -> None:
    try:
        config = load_config()
        validate_source_database(config.source)
        if not config.app_db_path.exists():
            raise FileNotFoundError(f"App DB not found: {config.app_db_path}")
        if not config.faiss_index_path.exists():
            raise FileNotFoundError(f"FAISS index not found: {config.faiss_index_path}")
        typer.echo("Doctor check passed")
    except (KeyError, SourceSchemaError, FileNotFoundError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
