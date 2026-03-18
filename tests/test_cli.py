import os
from pathlib import Path
from subprocess import CompletedProcess

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
    assert (tmp_path / ".dual-agents" / "analyze_image.py").exists()
    assert "Next steps:" in result.stdout


def test_explain_stop_classifies_timeout(tmp_path: Path) -> None:
    transcript = tmp_path / "stop.txt"
    transcript.write_text("Error: SSE read timed out\n")
    result = CliRunner().invoke(app, ["explain-stop", "--transcript-file", str(transcript)])
    assert result.exit_code == 0
    assert "Stop signal: STREAM_TIMEOUT" in result.stdout


def test_analyze_completeness_prints_schema_contract() -> None:
    result = CliRunner().invoke(app, ["analyze-completeness", "--describe-schema", "--data-root", "."])
    assert result.exit_code == 0
    assert "coverage_report.json" in result.stdout


def test_analyze_completeness_reads_explicit_brand_set(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    for brand in ("radpower", "ride1up", "super73", "aventon", "velotric"):
        brand_dir = data_root / brand
        brand_dir.mkdir(parents=True)
        (brand_dir / "coverage_report.json").write_text(
            "{\n"
            f'  "brand": "{brand}",\n'
            '  "products_attempted": 2,\n'
            '  "products_succeeded": 2,\n'
            '  "fields": {\n'
            '    "motor_power_watts": {"normalized_success": 2},\n'
            '    "battery_wh": {"normalized_success": 2},\n'
            '    "weight_lbs": {"normalized_success": 2},\n'
            '    "max_speed_mph": {"normalized_success": 2}\n'
            "  }\n"
            "}\n"
        )

    result = CliRunner().invoke(
        app,
        ["analyze-completeness", "--data-root", str(data_root), "--brand-set", "official"],
    )
    assert result.exit_code == 0
    assert "TECH SPEC COMPLETENESS ANALYSIS" in result.stdout
    assert "radpower" in result.stdout


def test_analyze_image_rejects_relative_paths(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "image.png"
    image_path.write_text("fake")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("dual_agents.cli.shutil.which", lambda name: "/usr/bin/codex")
    result = CliRunner().invoke(
        app,
        ["analyze-image", "--image-path", "image.png", "--prompt", "describe it"],
    )
    assert result.exit_code == 1
    assert "absolute file path" in result.stderr


def test_analyze_image_uses_codex_for_absolute_path(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "image.png"
    image_path.write_text("fake")
    monkeypatch.setattr("dual_agents.cli.shutil.which", lambda name: "/usr/bin/codex")
    monkeypatch.setattr(
        "dual_agents.cli.subprocess.run",
        lambda *args, **kwargs: CompletedProcess(args=args[0], returncode=0, stdout="image ok\n", stderr=""),
    )
    result = CliRunner().invoke(
        app,
        ["analyze-image", "--image-path", str(image_path.resolve()), "--prompt", "describe it"],
    )
    assert result.exit_code == 0
    assert "image ok" in result.stdout
