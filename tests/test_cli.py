import os
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
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


def test_review_gate_runs_codex_and_persists_lead_review(tmp_path: Path, monkeypatch) -> None:
    request_file = tmp_path / "review-request.txt"
    request_file.write_text("# Review Request\n\nPlease review this bounded unit.\n")

    def fake_run(command, cwd, capture_output, text, check):
        assert command[:4] == ["codex", "exec", "--model", "gpt-5.4"]
        assert cwd == tmp_path
        return CompletedProcess(
            command,
            0,
            stdout=(
                "1. Verdict: APPROVED\n"
                "2. Current unit status: NOT_STARTED\n"
                "3. Blocking issues: None\n"
                "4. Non-blocking issues: None\n"
                "5. Cause classification: NOT_APPLICABLE\n"
                "6. Delivery proof status: NOT_APPLICABLE\n"
                "7. Next bounded unit may start: YES\n"
                "8. Suggested next action: Start implementation for the bounded unit.\n"
            ),
            stderr="",
        )

    monkeypatch.setattr("dual_agents.cli.subprocess.run", fake_run)

    result = CliRunner().invoke(
        app,
        [
            "review-gate",
            "--unit-slug",
            "task-01-query-map",
            "--mode",
            "lead",
            "--request-file",
            str(request_file),
            "--repo-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    artifact_path = tmp_path / ".dual-agents" / "reviews" / "task-01-query-map" / "lead-review.txt"
    assert payload["artifact_path"] == str(artifact_path)
    assert artifact_path.exists()
    assert "Verdict: APPROVED" in artifact_path.read_text()
    state_path = tmp_path / ".dual-agents" / "run-state.json"
    assert payload["state_path"] == str(state_path)
    assert json.loads(state_path.read_text())["current_unit"]["unit_slug"] == "task-01-query-map"
    assert json.loads(state_path.read_text())["current_unit"]["stage"] == "implementation"


def test_review_gate_prepends_lead_mode_guidance(tmp_path: Path, monkeypatch) -> None:
    request_file = tmp_path / "review-request.txt"
    request_file.write_text("Plan for Task 01\n")

    def fake_run(command, cwd, capture_output, text, check):
        prompt = command[-1]
        assert "REVIEW MODE: LEAD" in prompt
        assert "PRE-IMPLEMENTATION design gate" in prompt
        assert "Do not request completed code" in prompt
        return CompletedProcess(
            command,
            0,
            stdout=(
                "1. Verdict: APPROVED\n"
                "2. Current unit status: NOT_STARTED\n"
                "3. Blocking issues: None\n"
                "4. Non-blocking issues: None\n"
                "5. Cause classification: NOT_APPLICABLE\n"
                "6. Delivery proof status: NOT_APPLICABLE\n"
                "7. Next bounded unit may start: YES\n"
                "8. Suggested next action: Start implementation for the bounded unit.\n"
            ),
            stderr="",
        )

    monkeypatch.setattr("dual_agents.cli.subprocess.run", fake_run)

    result = CliRunner().invoke(
        app,
        [
            "review-gate",
            "--unit-slug",
            "task-01-query-map",
            "--mode",
            "lead",
            "--request-file",
            str(request_file),
            "--repo-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0


def test_review_gate_validates_final_review_delivery_proof(tmp_path: Path, monkeypatch) -> None:
    request_file = tmp_path / "review-request.txt"
    request_file.write_text("# Review Request\n\nPlease review this bounded unit.\n")
    state_path = tmp_path / ".dual-agents" / "run-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "current_unit": {
                    "unit_slug": "task-02-metadata",
                    "stage": "critical_review",
                    "review_fix_rounds_used": 0,
                    "lead_review_required": False,
                    "critical_review_required": False,
                    "current_builder_task": None,
                    "current_builder_task_type": None,
                    "expected_lead_review_path": str(tmp_path / ".dual-agents" / "reviews" / "task-02-metadata" / "lead-review.txt"),
                    "expected_final_review_path": str(tmp_path / ".dual-agents" / "reviews" / "task-02-metadata" / "final-review.txt"),
                }
            }
        )
        + "\n"
    )

    def fake_run(command, cwd, capture_output, text, check):
        return CompletedProcess(
            command,
            0,
            stdout=(
                "1. Verdict: APPROVED\n"
                "2. Current unit status: PASS\n"
                "3. Blocking issues: None\n"
                "4. Non-blocking issues: None\n"
                "5. Cause classification: NOT_APPLICABLE\n"
                "6. Delivery proof status: PROVEN\n"
                "7. Next bounded unit may start: YES\n"
                "8. Suggested next action: Close the unit and move to the next bounded task.\n"
            ),
            stderr="",
        )

    monkeypatch.setattr("dual_agents.cli.subprocess.run", fake_run)

    result = CliRunner().invoke(
        app,
        [
            "review-gate",
            "--unit-slug",
            "task-02-metadata",
            "--mode",
            "final",
            "--request-file",
            str(request_file),
            "--repo-root",
            str(tmp_path),
            "--require-delivery-proof",
            "PROVEN",
        ],
    )

    assert result.exit_code == 0
    artifact_path = tmp_path / ".dual-agents" / "reviews" / "task-02-metadata" / "final-review.txt"
    assert artifact_path.exists()
    assert json.loads(state_path.read_text())["current_unit"]["stage"] == "adjudication"


def test_init_target_exports_assets_and_prints_next_steps(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GLM_API_KEY", "test-key")
    monkeypatch.setattr("dual_agents.cli.shutil.which", lambda name: f"/usr/bin/{name}")
    result = CliRunner().invoke(app, ["init-target", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / ".opencode" / "opencode.json").exists()
    assert (tmp_path / ".dual-agents" / "validate_report.py").exists()
    assert (tmp_path / ".dual-agents" / "validate_review.py").exists()
    assert (tmp_path / ".dual-agents" / "monitor_stop.py").exists()
    assert (tmp_path / ".dual-agents" / "analyze_image.py").exists()
    assert (tmp_path / ".dual-agents" / "endpoint_preflight.py").exists()
    assert (tmp_path / ".dual-agents" / "preflight_stage.py").exists()
    assert (tmp_path / ".dual-agents" / "require_worktree.py").exists()
    assert "Next steps:" in result.stdout


def test_explain_stop_classifies_timeout(tmp_path: Path) -> None:
    transcript = tmp_path / "stop.txt"
    transcript.write_text("Error: SSE read timed out\n")
    result = CliRunner().invoke(app, ["explain-stop", "--transcript-file", str(transcript)])
    assert result.exit_code == 0
    assert "Stop signal: STREAM_TIMEOUT" in result.stdout


def test_explain_stop_reports_background_service(tmp_path: Path) -> None:
    transcript = tmp_path / "stop.txt"
    transcript.write_text("$ python -m http.server 8000 --directory . &\n")
    result = CliRunner().invoke(app, ["explain-stop", "--transcript-file", str(transcript)])
    assert result.exit_code == 0
    assert "Stop signal: BACKGROUND_SERVICE" in result.stdout
    assert "local URL" in result.stdout


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


class _HeadOkHandler(BaseHTTPRequestHandler):
    def do_HEAD(self) -> None:  # noqa: N802
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def test_preflight_endpoint_succeeds_for_reachable_local_server() -> None:
    server = HTTPServer(("127.0.0.1", 0), _HeadOkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/health"
        result = CliRunner().invoke(app, ["preflight-endpoint", "--url", url])
        assert result.exit_code == 0
        assert "reachable" in result.stdout
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_preflight_endpoint_fails_for_bad_url() -> None:
    result = CliRunner().invoke(app, ["preflight-endpoint", "--url", "not-a-url"])
    assert result.exit_code == 1
    assert "absolute and use http or https" in result.stderr


def test_pre_completion_audit_passes_with_valid_final_review(tmp_path: Path) -> None:
    reviews_dir = tmp_path / ".dual-agents" / "reviews" / "task-02-metadata"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    (reviews_dir / "final-review.txt").write_text(
        "1. Verdict: APPROVED\n"
        "2. Current unit status: PASS\n"
        "3. Blocking issues: None\n"
        "4. Non-blocking issues: None\n"
        "5. Cause classification: NOT_APPLICABLE\n"
        "6. Delivery proof status: PROVEN\n"
        "7. Next bounded unit may start: YES\n"
        "8. Suggested next action: Close the unit and move to the next bounded task.\n"
    )
    state_path = tmp_path / ".dual-agents" / "run-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "current_unit": {
                    "unit_slug": "task-02-metadata",
                    "stage": "adjudication",
                    "review_fix_rounds_used": 0,
                    "lead_review_required": False,
                    "critical_review_required": False,
                    "current_builder_task": None,
                    "current_builder_task_type": None,
                    "expected_lead_review_path": str(tmp_path / ".dual-agents" / "reviews" / "task-02-metadata" / "lead-review.txt"),
                    "expected_final_review_path": str(reviews_dir / "final-review.txt"),
                }
            }
        )
        + "\n"
    )

    result = CliRunner().invoke(
        app,
        [
            "pre-completion-audit",
            "--repo-root",
            str(tmp_path),
            "--require-delivery-proof",
            "PROVEN",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["failures"] == []
    assert payload["audited_units"][0]["unit_slug"] == "task-02-metadata"


def test_pre_completion_audit_rejects_invalid_self_review_artifact(tmp_path: Path) -> None:
    reviews_dir = tmp_path / ".dual-agents" / "reviews" / "task-03-bad-review"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    (reviews_dir / "final-review.txt").write_text(
        "## Unit Status: APPROVED\n"
        "## Changes Summary\n"
        "- Added a guard\n"
        "## Acceptance Criteria Met\n"
        "- yes\n"
    )

    result = CliRunner().invoke(
        app,
        [
            "pre-completion-audit",
            "--repo-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["failures"]
    assert "self-review" in payload["failures"][0]["error"]


def test_start_unit_persists_run_state(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "start-unit",
            "--unit-slug",
            "task-01-query-map",
            "--repo-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    state_path = tmp_path / ".dual-agents" / "run-state.json"
    assert payload["state_path"] == str(state_path)
    saved = json.loads(state_path.read_text())
    assert saved["current_unit"]["unit_slug"] == "task-01-query-map"
    assert saved["current_unit"]["stage"] == "epic_review"
    assert saved["current_unit"]["required_next_artifacts"] == ["lead_review_artifact"]


def test_heartbeat_updates_run_state(tmp_path: Path) -> None:
    state_path = tmp_path / ".dual-agents" / "run-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "current_unit": {
                    "unit_slug": "task-01-query-map",
                    "stage": "implementation",
                    "started_at": "2026-03-30T00:00:00Z",
                    "updated_at": "2026-03-30T00:00:00Z",
                    "last_progress_at": "2026-03-30T00:00:00Z",
                    "last_heartbeat_at": None,
                    "review_fix_rounds_used": 0,
                    "lead_review_required": False,
                    "critical_review_required": False,
                    "current_builder_task": None,
                    "current_builder_task_type": None,
                    "expected_lead_review_path": str(tmp_path / ".dual-agents" / "reviews" / "task-01-query-map" / "lead-review.txt"),
                    "expected_final_review_path": str(tmp_path / ".dual-agents" / "reviews" / "task-01-query-map" / "final-review.txt"),
                    "required_next_artifacts": ["builder_result"],
                    "open_blocking_issues": [],
                    "last_stop_reason": None,
                    "idle_timeout_seconds": 300,
                    "hard_stop_timeout_seconds": 600,
                    "inactivity_stall_count": 0,
                }
            }
        )
        + "\n"
    )
    result = CliRunner().invoke(
        app,
        [
            "heartbeat",
            "--unit-slug",
            "task-01-query-map",
            "--repo-root",
            str(tmp_path),
            "--note",
            "Waiting on bounded builder handoff result",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["note"] == "Waiting on bounded builder handoff result"
    saved = json.loads(state_path.read_text())
    assert saved["current_unit"]["last_heartbeat_at"] is not None


def test_watchdog_check_marks_unit_stalled_after_timeout(tmp_path: Path) -> None:
    state_path = tmp_path / ".dual-agents" / "run-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "current_unit": {
                    "unit_slug": "task-01-query-map",
                    "stage": "implementation",
                    "started_at": "2000-01-01T00:00:00Z",
                    "updated_at": "2000-01-01T00:00:00Z",
                    "last_progress_at": "2000-01-01T00:00:00Z",
                    "last_heartbeat_at": None,
                    "review_fix_rounds_used": 0,
                    "lead_review_required": False,
                    "critical_review_required": False,
                    "current_builder_task": None,
                    "current_builder_task_type": None,
                    "expected_lead_review_path": str(tmp_path / ".dual-agents" / "reviews" / "task-01-query-map" / "lead-review.txt"),
                    "expected_final_review_path": str(tmp_path / ".dual-agents" / "reviews" / "task-01-query-map" / "final-review.txt"),
                    "required_next_artifacts": ["builder_result"],
                    "open_blocking_issues": [],
                    "last_stop_reason": None,
                    "idle_timeout_seconds": 300,
                    "hard_stop_timeout_seconds": 600,
                    "inactivity_stall_count": 0,
                }
            }
        )
        + "\n"
    )
    result = CliRunner().invoke(app, ["watchdog-check", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "stalled"
    saved = json.loads(state_path.read_text())
    assert saved["current_unit"]["stage"] == "stalled"
    assert saved["current_unit"]["last_stop_reason"]


def test_stop_unit_records_explicit_stall_reason(tmp_path: Path) -> None:
    state_path = tmp_path / ".dual-agents" / "run-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "current_unit": {
                    "unit_slug": "task-09-remediation",
                    "stage": "implementation",
                    "started_at": "2026-03-30T00:00:00Z",
                    "updated_at": "2026-03-30T00:00:00Z",
                    "last_progress_at": "2026-03-30T00:00:00Z",
                    "last_heartbeat_at": None,
                    "review_fix_rounds_used": 0,
                    "lead_review_required": False,
                    "critical_review_required": False,
                    "current_builder_task": None,
                    "current_builder_task_type": None,
                    "expected_lead_review_path": str(tmp_path / ".dual-agents" / "reviews" / "task-09-remediation" / "lead-review.txt"),
                    "expected_final_review_path": str(tmp_path / ".dual-agents" / "reviews" / "task-09-remediation" / "final-review.txt"),
                    "required_next_artifacts": ["builder_result"],
                    "open_blocking_issues": [],
                    "last_stop_reason": None,
                    "idle_timeout_seconds": 300,
                    "hard_stop_timeout_seconds": 600,
                    "inactivity_stall_count": 0,
                }
            }
        )
        + "\n"
    )
    result = CliRunner().invoke(
        app,
        [
            "stop-unit",
            "--unit-slug",
            "task-09-remediation",
            "--repo-root",
            str(tmp_path),
            "--reason",
            "Launcher schema missing subagent_type.",
        ],
    )
    assert result.exit_code == 0
    saved = json.loads(state_path.read_text())
    assert saved["current_unit"]["stage"] == "stalled"
    assert saved["current_unit"]["last_stop_reason"] == "Launcher schema missing subagent_type."
