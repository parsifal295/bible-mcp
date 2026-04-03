import typer

app = typer.Typer(help="Korean Bible MCP server")


@app.command()
def index() -> None:
    """Build local search indexes from the source Bible database."""
    raise typer.Exit(code=0)


@app.command()
def serve() -> None:
    """Run the MCP server over stdio."""
    raise typer.Exit(code=0)


@app.command()
def doctor() -> None:
    """Validate local configuration and index files."""
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
