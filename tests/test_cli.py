import os
from pathlib import Path

from typer.testing import CliRunner

from dual_agents.cli import app


def test_cli_shows_help() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "dual-agent workflow" in result.stdout.lower()


def test_doctor_fails_when_required_tools_or_env_are_missing(monkeypatch) -> None:
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    monkeypatch.setattr("dual_agents.cli.shutil.which", lambda name: None)
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "GLM_API_KEY" in result.stdout


def test_init_target_exports_assets_and_prints_next_steps(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GLM_API_KEY", "test-key")
    monkeypatch.setattr("dual_agents.cli.shutil.which", lambda name: f"/usr/bin/{name}")
    result = CliRunner().invoke(app, ["init-target", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / ".opencode" / "opencode.json").exists()
    assert (tmp_path / ".dual-agents" / "validate_report.py").exists()
    assert (tmp_path / ".dual-agents" / "monitor_stop.py").exists()
    assert "Next steps:" in result.stdout


def test_explain_stop_classifies_timeout(tmp_path: Path) -> None:
    transcript = tmp_path / "stop.txt"
    transcript.write_text("Error: SSE read timed out\n")
    result = CliRunner().invoke(app, ["explain-stop", "--transcript-file", str(transcript)])
    assert result.exit_code == 0
    assert "Stop signal: STREAM_TIMEOUT" in result.stdout
