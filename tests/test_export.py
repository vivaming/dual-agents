from pathlib import Path

from typer.testing import CliRunner

from dual_agents.cli import app


def test_export_writes_expected_files(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["export", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / ".opencode" / ".gitignore").exists()
    assert (tmp_path / ".opencode" / "opencode.json").exists()
    assert (tmp_path / ".opencode" / "agents" / "glm-builder.md").exists()
    assert (tmp_path / ".opencode" / "commands" / "dual.md").exists()
    assert (tmp_path / ".dual-agents" / "codex-review.txt").exists()
    assert (tmp_path / ".dual-agents" / "validate_report.py").exists()
    assert (tmp_path / ".dual-agents" / "monitor_stop.py").exists()
    validator = (tmp_path / ".dual-agents" / "validate_report.py").read_text()
    assert "--mode" in validator
    assert "post-review" in validator
    assert "forum" in validator


def test_export_prunes_known_transient_opencode_runtime_files(tmp_path: Path) -> None:
    opencode_dir = tmp_path / ".opencode"
    (opencode_dir / "node_modules" / "zod").mkdir(parents=True)
    (opencode_dir / "node_modules" / "zod" / "index.js").write_text("module.exports = {};\n")
    (opencode_dir / "package.json").write_text("{}\n")
    (opencode_dir / "bun.lock").write_text("lock\n")

    result = CliRunner().invoke(app, ["export", "--output-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert not (opencode_dir / "node_modules").exists()
    assert not (opencode_dir / "package.json").exists()
    assert not (opencode_dir / "bun.lock").exists()
