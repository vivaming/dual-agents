import os
import json
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
    assert (tmp_path / ".dual-agents" / "validate_review.py").exists()
    assert (tmp_path / ".dual-agents" / "monitor_stop.py").exists()
    assert "Next steps:" in result.stdout


def test_explain_stop_reports_background_service(tmp_path: Path) -> None:
    transcript_file = tmp_path / "transcript.txt"
    transcript_file.write_text("$ python -m http.server 8000 --directory . &\n")

    result = CliRunner().invoke(
        app,
        [
            "explain-stop",
            "--transcript-file",
            str(transcript_file),
            "--unit-name",
            "local server bootstrap",
        ],
    )

    assert result.exit_code == 0
    assert "Stop signal: BACKGROUND_SERVICE" in result.stdout
    assert "local URL" in result.stdout


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


def test_review_gate_compacts_structured_request_before_codex(tmp_path: Path, monkeypatch) -> None:
    request_file = tmp_path / "review-request.txt"
    request_file.write_text(
        "# Review Request: Packet hygiene\n\n"
        "## Decision Needed\n"
        "- Decide whether the bounded unit can advance.\n\n"
        "## Evidence Files\n"
        "- /tmp/a.md\n"
        "- /tmp/a.md\n"
        "- /tmp/b.md\n\n"
        "## Facts Observed\n"
        "- duplicate fact\n"
        "- duplicate fact\n\n"
        "## Open Questions\n"
        "1. Can the next bounded unit start?\n"
        "2. Can the next bounded unit start?\n\n"
        "## Required Output Format\n"
        "- This section should not be forwarded.\n"
    )

    def fake_run(command, cwd, capture_output, text, check):
        prompt = command[-1]
        assert "# Review Request: Packet hygiene" in prompt
        assert prompt.count("- /tmp/a.md") == 1
        assert prompt.count("duplicate fact") == 1
        assert prompt.count("Can the next bounded unit start?") == 1
        assert "Required Output Format" not in prompt
        return CompletedProcess(
            command,
            0,
            stdout=(
                "1. Verdict: APPROVED\n"
                "2. Current unit status: PASS\n"
                "3. Blocking issues: None\n"
                "4. Non-blocking issues: None\n"
                "5. Cause classification: NOT_APPLICABLE\n"
                "6. Delivery proof status: NOT_APPLICABLE\n"
                "7. Next bounded unit may start: YES\n"
                "8. Suggested next action: Start the next bounded unit.\n"
            ),
            stderr="",
        )

    monkeypatch.setattr("dual_agents.cli.subprocess.run", fake_run)
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


def test_review_gate_saves_malformed_review_to_invalid_sidecar(tmp_path: Path, monkeypatch) -> None:
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
            stdout="1. Verdict: APPROVED\n",
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
        ],
    )

    assert result.exit_code != 0
    artifact_path = tmp_path / ".dual-agents" / "reviews" / "task-02-metadata" / "final-review.txt"
    invalid_path = tmp_path / ".dual-agents" / "reviews" / "task-02-metadata" / "final-review.invalid.txt"
    assert not artifact_path.exists()
    assert invalid_path.exists()
    assert invalid_path.read_text() == "1. Verdict: APPROVED\n"


def test_submit_review_artifact_advances_without_running_codex(tmp_path: Path, monkeypatch) -> None:
    review_file = tmp_path / ".dual-agents" / "reviews" / "task-03-collection-upgrades" / "final-review.txt"
    review_file.parent.mkdir(parents=True, exist_ok=True)
    review_file.write_text(
        "1. Verdict: APPROVED\n"
        "2. Current unit status: PASS\n"
        "3. Blocking issues: None\n"
        "4. Non-blocking issues: None\n"
        "5. Cause classification: NOT_APPLICABLE\n"
        "6. Delivery proof status: NOT_APPLICABLE\n"
        "7. Next bounded unit may start: YES\n"
        "8. Suggested next action: Start the next bounded unit.\n"
    )
    state_path = tmp_path / ".dual-agents" / "run-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "current_unit": {
                    "unit_slug": "task-03-collection-upgrades",
                    "stage": "stalled",
                    "review_fix_rounds_used": 0,
                    "lead_review_required": False,
                    "critical_review_required": False,
                    "current_builder_task": None,
                    "current_builder_task_type": None,
                    "expected_lead_review_path": str(tmp_path / ".dual-agents" / "reviews" / "task-03-collection-upgrades" / "lead-review.txt"),
                    "expected_final_review_path": str(review_file),
                }
            }
        )
        + "\n"
    )

    def fail_run(*args, **kwargs):
        raise AssertionError("subprocess.run should not be called for submit-review-artifact")

    monkeypatch.setattr("dual_agents.cli.subprocess.run", fail_run)

    result = CliRunner().invoke(
        app,
        [
            "submit-review-artifact",
            "--unit-slug",
            "task-03-collection-upgrades",
            "--mode",
            "final",
            "--review-file",
            str(review_file),
            "--repo-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["artifact_path"] == str(review_file)
    assert payload["stage"] == "adjudication"
    assert json.loads(state_path.read_text())["current_unit"]["stage"] == "adjudication"


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
    assert payload["start_mode"] == "auto"
    assert "decision_reason" in payload
    saved = json.loads(state_path.read_text())
    assert saved["current_unit"]["unit_slug"] == "task-01-query-map"
    assert saved["current_unit"]["stage"] == "implementation"
    assert saved["current_unit"]["required_next_artifacts"] == ["builder_result"]


def test_start_unit_auto_can_begin_with_review(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "start-unit",
            "--unit-slug",
            "task-01-query-map",
            "--repo-root",
            str(tmp_path),
            "--task-summary",
            "Run a pre-implementation design review for this spec before any code changes.",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    state_path = tmp_path / ".dual-agents" / "run-state.json"
    saved = json.loads(state_path.read_text())
    assert payload["start_mode"] == "auto"
    assert saved["current_unit"]["stage"] == "epic_review"
    assert saved["current_unit"]["required_next_artifacts"] == ["lead_review_artifact"]


def test_start_unit_auto_can_use_explicit_task_file(tmp_path: Path) -> None:
    task_file = tmp_path / "task.md"
    task_file.write_text("# Task\n\nRun a pre-implementation design review for this architecture plan.")

    result = CliRunner().invoke(
        app,
        [
            "start-unit",
            "--unit-slug",
            "task-01-query-map",
            "--repo-root",
            str(tmp_path),
            "--task-file",
            str(task_file),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    state_path = tmp_path / ".dual-agents" / "run-state.json"
    saved = json.loads(state_path.read_text())
    assert payload["task_file"] == str(task_file)
    assert saved["current_unit"]["stage"] == "epic_review"


def test_start_unit_auto_discovers_epic_task_file(tmp_path: Path) -> None:
    task_file = tmp_path / "epic" / "my-epic" / "03-task-query-map.md"
    task_file.parent.mkdir(parents=True, exist_ok=True)
    task_file.write_text("# Task\n\nThis is a design gate. Review the spec before implementation.")

    result = CliRunner().invoke(
        app,
        [
            "start-unit",
            "--unit-slug",
            "task-03-query-map",
            "--repo-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    state_path = tmp_path / ".dual-agents" / "run-state.json"
    saved = json.loads(state_path.read_text())
    assert payload["task_file"] == str(task_file)
    assert saved["current_unit"]["stage"] == "epic_review"


def test_start_unit_auto_prefers_implementation_for_delivery_shaped_task_file(tmp_path: Path) -> None:
    task_file = tmp_path / "epic" / "my-epic" / "03-task-query-map.md"
    task_file.parent.mkdir(parents=True, exist_ok=True)
    task_file.write_text(
        "# Task\n\n"
        "## Files\n- Modify: data/collection_definitions.json\n\n"
        "## Required Changes\nImplement the collection update.\n\n"
        "## Acceptance Criteria\nRendered output contains the new section.\n\n"
        "## Verification\npython3 scripts/generate.py --dry-run\n"
    )

    result = CliRunner().invoke(
        app,
        [
            "start-unit",
            "--unit-slug",
            "task-03-query-map",
            "--repo-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    state_path = tmp_path / ".dual-agents" / "run-state.json"
    saved = json.loads(state_path.read_text())
    assert saved["current_unit"]["stage"] == "implementation"
    assert payload["implementation_score"] >= payload["review_score"]


def test_start_unit_explicit_review_mode_overrides_default(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "start-unit",
            "--unit-slug",
            "task-01-query-map",
            "--repo-root",
            str(tmp_path),
            "--start-mode",
            "review",
        ],
    )

    assert result.exit_code == 0
    state_path = tmp_path / ".dual-agents" / "run-state.json"
    saved = json.loads(state_path.read_text())
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
