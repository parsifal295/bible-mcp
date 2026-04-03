## bible-mcp

`bible-mcp` is a local-first Korean Bible MCP server. It imports verses from a source SQLite database, builds passage chunks and search indexes, and serves those indexes through an MCP server.

V2 metadata slice: `bible-mcp index` also imports the repo-managed metadata fixtures so optional entity search and entity relation MCP tools can be enabled at serve time when the metadata tables are present.

## Setup

1. Create and activate a virtual environment.
2. Install the project in editable mode with dev dependencies:
   `pip install -e '.[dev]'`
3. Set `BIBLE_SOURCE_DB` to a SQLite database that contains the source `verses` table. The importer expects at least `book`, `chapter`, `verse`, and `text`, and it can also read optional `translation`.
4. Run indexing:
   `bible-mcp index`
5. Start the MCP server:
   `bible-mcp serve`

## Commands

- `bible-mcp index` imports the source verses and metadata fixtures into the app database, rebuilds chunks and FTS indexes, and writes FAISS embeddings.
- `bible-mcp serve` validates the app database and FAISS artifacts, then starts the MCP server. When optional metadata tables are available it also exposes entity search and entity relation tools.
- `bible-mcp doctor` validates the source database and the generated runtime artifacts without starting the server.
