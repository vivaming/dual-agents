from typer.testing import CliRunner

from dual_agents.cli import app


def test_cli_shows_help() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "dual-agent workflow" in result.stdout.lower()
