import sqlite3


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists verses (
            id integer primary key,
            translation text,
            book text not null,
            book_order integer not null,
            chapter integer not null,
            verse integer not null,
            reference text not null unique,
            testament text,
            text text not null
        );

        create table if not exists passage_chunks (
            id integer primary key,
            chunk_id text not null unique,
            start_ref text not null,
            end_ref text not null,
            book text not null,
            chapter_range text not null,
            text text not null,
            token_count integer not null,
            chunk_strategy text not null
        );

        create virtual table if not exists verses_fts using fts5(
            reference,
            text,
            content='',
            tokenize='unicode61'
        );

        create virtual table if not exists passage_chunks_fts using fts5(
            chunk_id,
            text,
            content='',
            tokenize='unicode61'
        );

        create table if not exists chunk_embeddings (
            chunk_id text primary key,
            model_name text not null,
            embedding_version text not null,
            updated_at text not null
        );

        create table if not exists people (
            id integer primary key,
            slug text not null unique,
            display_name text not null,
            description text
        );

        create table if not exists events (
            id integer primary key,
            slug text not null unique,
            display_name text not null,
            description text
        );

        create table if not exists places (
            id integer primary key,
            slug text not null unique,
            display_name text not null,
            latitude real,
            longitude real
        );

        create table if not exists entity_aliases (
            id integer primary key,
            entity_type text not null,
            entity_slug text not null,
            alias text not null
        );

        create table if not exists entity_verse_links (
            id integer primary key,
            entity_type text not null,
            entity_slug text not null,
            reference text not null
        );

        create table if not exists entity_relationships (
            id integer primary key,
            source_type text not null,
            source_slug text not null,
            relation_type text not null,
            target_type text not null,
            target_slug text not null,
            is_primary integer not null default 0,
            note text
        );

        create index if not exists idx_entity_relationships_source
        on entity_relationships(source_type, source_slug);

        create index if not exists idx_entity_relationships_target
        on entity_relationships(target_type, target_slug);
        """
    )
    conn.commit()
