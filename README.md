## bible-mcp

`bible-mcp` is a local-first Korean Bible MCP server. It imports verses from a source SQLite database, builds passage chunks and search indexes, and serves those indexes through an MCP server.

V2 metadata slice: metadata is fetched and synced explicitly before indexing. `bible-mcp index` now depends on metadata that was already synced into the app DB.

V2 entity search defaults to `people` for backwards compatibility; to search bundled place or event metadata, call `search_entities` with an explicit `entity_type` such as `places` or `events`.

## Setup

1. Create and activate a virtual environment.
2. Install the project in editable mode with dev dependencies:
   `pip install -e '.[dev]'`
3. Set `BIBLE_SOURCE_DB` to a SQLite database that contains the source `verses` table. The importer expects at least `book`, `chapter`, `verse`, and `text`, and it can also read optional `translation`.
4. Fetch theographic metadata snapshot:
   `bible-mcp fetch-theographic`
5. Sync fetched metadata into the app DB:
   `bible-mcp sync-theographic`
6. Run indexing (offline; does not fetch metadata remotely):
   `bible-mcp index`
7. Start the MCP server:
   `bible-mcp serve`

## Commands

- `bible-mcp fetch-theographic` downloads the configured theographic snapshot into the local vendor directory.
- `bible-mcp sync-theographic` normalizes the fetched snapshot and syncs metadata rows into the app database.
- `bible-mcp index` imports source verses, requires already-synced metadata, rebuilds chunks and FTS indexes, and writes FAISS embeddings. It is offline and does not fetch metadata remotely.
- `bible-mcp serve` validates the app database and FAISS artifacts, then starts the MCP server. When optional metadata tables are available it also exposes entity search and entity relation tools.
- `bible-mcp doctor` validates the source database and the generated runtime artifacts without starting the server.
