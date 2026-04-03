import os
import sqlite3
from pathlib import Path

import typer

from bible_mcp.config import AppConfig, SourceBibleConfig, TheographicConfig
from bible_mcp.db.connection import connect_db
from bible_mcp.db.schema import ensure_schema
from bible_mcp.index.embeddings import SentenceTransformerEmbedder, index_chunk_embeddings
from bible_mcp.index.faiss_store import FaissChunkIndex
from bible_mcp.index.fts import rebuild_fts_indexes
from bible_mcp.ingest.chunker import build_chunks
from bible_mcp.ingest.importer import import_verses
from bible_mcp.ingest.metadata_importer import import_metadata_fixtures
from bible_mcp.ingest.source_db import SourceSchemaError, validate_source_database
from bible_mcp.mcp_server import create_mcp_server
from bible_mcp.services.entity_query_router import EntityQueryRouter
from bible_mcp.services.entity_service import EntityService
from bible_mcp.services.entity_passage_service import EntityPassageService
from bible_mcp.services.related_service import RelatedPassageService
from bible_mcp.services.passage_service import PassageService
from bible_mcp.services.relation_service import RelationLookupService
from bible_mcp.services.search_service import SearchService
from bible_mcp.services.summarizer import summarize_passage_text
from bible_mcp.vendor.theographic_fetcher import fetch_theographic_snapshot

app = typer.Typer(help="Korean Bible MCP server")
REQUIRED_APP_DB_TABLES = ("verses", "passage_chunks", "passage_chunks_fts")
OPTIONAL_STUDY_DB_TABLES = ("people", "entity_aliases")
OPTIONAL_RELATION_DB_TABLES = ("entity_relationships",)


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def load_config() -> AppConfig:
    source_path = Path(_required_env("BIBLE_SOURCE_DB"))
    source_table = os.environ.get("BIBLE_SOURCE_TABLE", "verses")
    app_db_path = Path(os.environ.get("BIBLE_APP_DB", "data/app.sqlite"))
    faiss_index_path = Path(os.environ.get("BIBLE_FAISS_INDEX", "data/chunks.faiss"))
    app_db_path.parent.mkdir(parents=True, exist_ok=True)
    faiss_index_path.parent.mkdir(parents=True, exist_ok=True)
    return AppConfig(
        source=SourceBibleConfig(path=source_path, table=source_table),
        app_db_path=app_db_path,
        faiss_index_path=faiss_index_path,
        theographic=load_theographic_config(),
    )


def load_theographic_config() -> TheographicConfig:
    repo = os.environ.get("THEOGRAPHIC_REPO", "robertrouse/theographic-bible-metadata")
    ref = os.environ.get("THEOGRAPHIC_REF", "master")
    vendor_dir = Path(
        os.environ.get("THEOGRAPHIC_VENDOR_DIR", "data/vendor/theographic")
    )
    link_limit = int(os.environ.get("THEOGRAPHIC_LINK_LIMIT", "20"))
    vendor_dir.mkdir(parents=True, exist_ok=True)
    return TheographicConfig(
        repo=repo,
        ref=ref,
        vendor_dir=vendor_dir,
        link_limit=link_limit,
    )


def validate_runtime_installation(config: AppConfig) -> FaissChunkIndex:
    if not config.app_db_path.exists():
        raise FileNotFoundError(f"App DB not found: {config.app_db_path}")

    try:
        conn = sqlite3.connect(f"file:{config.app_db_path}?mode=ro", uri=True)
        try:
            missing_tables = [
                table
                for table in REQUIRED_APP_DB_TABLES
                if conn.execute(
                    "select 1 from sqlite_master where type = 'table' and name = ?",
                    (table,),
                ).fetchone()
                is None
            ]
            if not missing_tables:
                passage_chunk_ids = [
                    row[0]
                    for row in conn.execute(
                        "select chunk_id from passage_chunks order by id"
                    ).fetchall()
                ]
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise RuntimeError(f"App DB is not usable: {config.app_db_path}") from exc

    if missing_tables:
        raise RuntimeError(
            "App DB is missing required tables: " + ", ".join(missing_tables)
        )

    vector_store = FaissChunkIndex(config.faiss_index_path)
    try:
        vector_store.load()
        if sorted(vector_store.id_map) != sorted(passage_chunk_ids):
            raise RuntimeError(
                "FAISS mapping ids do not match passage_chunks in app DB"
            )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"FAISS artifacts are missing or incomplete: {config.faiss_index_path}"
        ) from exc
    return vector_store


def _app_db_supports_optional_study_tools(config: AppConfig) -> bool:
    return _app_db_has_tables(config, OPTIONAL_STUDY_DB_TABLES)


def _app_db_supports_entity_passage_tools(config: AppConfig) -> bool:
    return _app_db_has_tables(
        config,
        OPTIONAL_STUDY_DB_TABLES + ("entity_verse_links",),
    )


def _app_db_supports_relation_tools(config: AppConfig) -> bool:
    return _app_db_has_tables(
        config,
        OPTIONAL_STUDY_DB_TABLES + OPTIONAL_RELATION_DB_TABLES,
    )


def _app_db_has_tables(config: AppConfig, tables: tuple[str, ...]) -> bool:
    conn = sqlite3.connect(f"file:{config.app_db_path}?mode=ro", uri=True)
    try:
        for table in tables:
            if (
                conn.execute(
                    "select 1 from sqlite_master where type = 'table' and name = ?",
                    (table,),
                ).fetchone()
                is None
            ):
                return False
    finally:
        conn.close()
    return True


@app.command()
def index() -> None:
    config = load_config()
    validate_source_database(config.source)
    conn = connect_db(config.app_db_path)
    ensure_schema(conn)
    import_verses(config, conn)
    import_metadata_fixtures(conn)
    build_chunks(conn)
    rebuild_fts_indexes(conn)
    embedder = SentenceTransformerEmbedder(config.embeddings.model_name)
    vector_store = FaissChunkIndex(config.faiss_index_path)
    index_chunk_embeddings(conn, embedder, vector_store)
    typer.echo("Index build complete")


@app.command("fetch-theographic")
def fetch_theographic() -> None:
    theographic_config = load_theographic_config()
    snapshot_path = fetch_theographic_snapshot(theographic_config)
    typer.echo(f"Theographic snapshot fetched: {snapshot_path}")


@app.command()
def serve() -> None:
    try:
        config = load_config()
        vector_store = validate_runtime_installation(config)
        conn = connect_db(config.app_db_path)
        embedder = SentenceTransformerEmbedder(config.embeddings.model_name)
        search_service = SearchService(conn, embedder, vector_store)
        passage_service = PassageService(conn)
        if _app_db_supports_optional_study_tools(config):
            related_service = RelatedPassageService(conn, embedder, vector_store)
            entity_service = EntityService(conn)
            summarizer = summarize_passage_text
            relation_service = None
            if _app_db_supports_relation_tools(config):
                relation_service = RelationLookupService(conn, entity_service)
            entity_passage_service = None
            if _app_db_supports_entity_passage_tools(config):
                entity_passage_service = EntityPassageService(
                    conn,
                    entity_service,
                    passage_service,
                )
            entity_query_router = EntityQueryRouter(
                entity_service,
                relation_service=relation_service,
                entity_passage_service=entity_passage_service,
            )
        else:
            related_service = None
            entity_service = None
            entity_passage_service = None
            summarizer = None
            relation_service = None
            entity_query_router = None
        create_mcp_server(
            search_service=search_service,
            passage_service=passage_service,
            related_service=related_service,
            summarizer=summarizer,
            entity_service=entity_service,
            relation_service=relation_service,
            entity_passage_service=entity_passage_service,
            entity_query_router=entity_query_router,
        ).run()
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)


@app.command()
def doctor() -> None:
    try:
        config = load_config()
        validate_source_database(config.source)
        validate_runtime_installation(config)
        typer.echo("Doctor check passed")
    except (KeyError, SourceSchemaError, FileNotFoundError, RuntimeError, ValueError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
