from pathlib import Path

from typer.testing import CliRunner

from dual_agents.cli import app


def test_export_writes_expected_files(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["export", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / ".opencode" / "opencode.json").exists()
    assert (tmp_path / ".opencode" / "agents" / "glm-builder.md").exists()
    assert (tmp_path / ".opencode" / "commands" / "dual.md").exists()
    assert (tmp_path / ".dual-agents" / "codex-review.txt").exists()
    assert (tmp_path / ".dual-agents" / "validate_report.py").exists()
    validator = (tmp_path / ".dual-agents" / "validate_report.py").read_text()
    assert "--mode" in validator
    assert "post-review" in validator
    assert "forum" in validator
