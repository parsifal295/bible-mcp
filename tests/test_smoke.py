from typer.testing import CliRunner

from bible_mcp.cli import app


def test_cli_help_shows_core_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "index" in result.stdout
    assert "serve" in result.stdout
    assert "doctor" in result.stdout
