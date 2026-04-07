from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import typer
import dual_agents.stop_monitor as stop_monitor_module

from dual_agents.codex_review import build_review_command, build_review_prompt
from dual_agents.config import AgentConfig, ProviderConfig, ReviewerConfig, WorkflowConfig
from dual_agents.controller import (
    BoundedUnitStartMode,
    DeliveryProofStatus,
    ReviewGateMode,
    WorkflowController,
    WorkflowStage,
    WorkflowViolation,
    choose_initial_stage,
    parse_review_result,
    validate_review_result,
)
from dual_agents.opencode_assets import build_agent_markdown, build_command_markdown, build_opencode_config
from dual_agents.stop_monitor import classify_stop, format_stop_report
from dual_agents.state import (
    RunState,
    apply_run_state,
    build_bounded_unit_state,
    default_state_path,
    load_run_state,
    mark_heartbeat,
    mark_progress,
    mark_stalled,
    save_run_state,
)
from dual_agents.watchdog import WatchdogStatus, evaluate_watchdog

app = typer.Typer(help="CLI for the dual-agent workflow.", no_args_is_help=True)
TRANSIENT_OPCODE_PATHS = (
    Path(".opencode") / "node_modules",
    Path(".opencode") / "package.json",
    Path(".opencode") / "bun.lock",
)


def build_report_validator_script() -> str:
    return """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

INTERNAL_LEAK_PATTERNS = (
    re.compile(r"^\\s*Thinking:\\s*", re.IGNORECASE | re.MULTILINE),
    re.compile(r"<(?:system|parameter|invoke)\\b", re.IGNORECASE),
    re.compile(r"^\\s*#\\s+Analyze\\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\\s*\\$\\s+python", re.IGNORECASE | re.MULTILINE),
)


def contains_internal_leak(raw_output: str) -> bool:
    return any(pattern.search(raw_output) for pattern in INTERNAL_LEAK_PATTERNS)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a user-facing dual-agent report.")
    parser.add_argument(
        "--mode",
        choices=("summary", "post-review", "forum"),
        default="summary",
        help="Validation mode.",
    )
    parser.add_argument("--report-file", type=Path, help="Path to a file containing the report text.")
    parser.add_argument("--require-term", action="append", default=[], help="Term that must appear in the report.")
    parser.add_argument("--max-issues", type=int, default=3, help="Maximum issue bullets for post-review mode.")
    parser.add_argument(
        "--max-perspectives",
        type=int,
        default=3,
        help="Maximum perspective bullets for forum mode.",
    )
    args = parser.parse_args()

    if args.report_file:
        text = args.report_file.read_text()
    else:
        text = sys.stdin.read()

    cleaned = text.strip()
    if not cleaned:
        print("ERROR: user-facing report must not be empty.", file=sys.stderr)
        return 1
    if contains_internal_leak(cleaned):
        print("ERROR: user-facing report leaked internal reasoning, tool syntax, or control tags.", file=sys.stderr)
        return 1

    missing_terms = [term for term in args.require_term if term not in cleaned]
    if missing_terms:
        print(
            "ERROR: user-facing report omitted required requested content: " + ", ".join(missing_terms),
            file=sys.stderr,
        )
        return 1

    if args.mode == "post-review":
        required_labels = (
            "Current unit status:",
            "Blocking issues:",
            "Next remediation unit:",
        )
        missing_labels = [label for label in required_labels if label not in cleaned]
        if missing_labels:
            print(
                "ERROR: post-review adjudication missing required labels: " + ", ".join(missing_labels),
                file=sys.stderr,
            )
            return 1
        issue_lines = [
            line for line in cleaned.splitlines()
            if line.strip().startswith("- ") and "Blocking issues:" not in line
        ]
        if len(issue_lines) > args.max_issues:
            print(
                f"ERROR: post-review adjudication listed {len(issue_lines)} issues; limit is {args.max_issues}.",
                file=sys.stderr,
            )
            return 1
        if len(cleaned) > 1800:
            print("ERROR: post-review adjudication is too long; keep it concise and bounded.", file=sys.stderr)
            return 1
    elif args.mode == "forum":
        required_labels = (
            "Current dispute:",
            "Perspectives:",
            "Moderator ruling:",
            "Next bounded action:",
        )
        missing_labels = [label for label in required_labels if label not in cleaned]
        if missing_labels:
            print(
                "ERROR: forum ruling missing required labels: " + ", ".join(missing_labels),
                file=sys.stderr,
            )
            return 1
        perspective_lines = [
            line for line in cleaned.splitlines()
            if line.strip().startswith("- ") and "Perspectives:" not in line
        ]
        if len(perspective_lines) > args.max_perspectives:
            print(
                f"ERROR: forum ruling listed {len(perspective_lines)} perspectives; limit is {args.max_perspectives}.",
                file=sys.stderr,
            )
            return 1
        if len(cleaned) > 1600:
            print("ERROR: forum ruling is too long; keep it concise and bounded.", file=sys.stderr)
            return 1

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def build_review_validator_script() -> str:
    return """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

VALID_VERDICTS = {"APPROVED", "CHANGES_REQUESTED"}
VALID_STATUSES = {"NOT_STARTED", "IN_PROGRESS", "PASS", "PASS_WITH_EXCEPTION", "CHANGES_REQUIRED", "BLOCKED", "STALLED"}
VALID_CAUSES = {"INTERNAL", "EXTERNAL", "MIXED", "NOT_APPLICABLE"}
VALID_DELIVERY = {"PROVEN", "NOT_PROVEN", "NOT_APPLICABLE"}
VALID_PROGRESS = {"YES", "NO"}
SELF_REVIEW_MARKERS = (
    re.compile(r"^\\s*##\\s+Unit Status:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\\s*##\\s+Changes Summary\\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\\s*##\\s+Acceptance Criteria Met\\b", re.IGNORECASE | re.MULTILINE),
)

FIELD_PATTERNS = {
    "verdict": re.compile(r"^\\s*(?:\\d+\\.\\s*)?Verdict:\\s*(.+?)\\s*$", re.IGNORECASE),
    "current_unit_status": re.compile(r"^\\s*(?:\\d+\\.\\s*)?Current unit status:\\s*(.+?)\\s*$", re.IGNORECASE),
    "blocking_issues": re.compile(r"^\\s*(?:\\d+\\.\\s*)?Blocking issues:?\\s*(.*?)\\s*$", re.IGNORECASE),
    "non_blocking_issues": re.compile(r"^\\s*(?:\\d+\\.\\s*)?Non-blocking issues:?\\s*(.*?)\\s*$", re.IGNORECASE),
    "cause_classification": re.compile(r"^\\s*(?:\\d+\\.\\s*)?Cause classification:\\s*(.+?)\\s*$", re.IGNORECASE),
    "delivery_proof_status": re.compile(r"^\\s*(?:\\d+\\.\\s*)?Delivery proof status:\\s*(.+?)\\s*$", re.IGNORECASE),
    "next_bounded_unit_may_start": re.compile(r"^\\s*(?:\\d+\\.\\s*)?Next bounded unit may start:\\s*(.+?)\\s*$", re.IGNORECASE),
    "suggested_next_action": re.compile(r"^\\s*(?:\\d+\\.\\s*)?Suggested next action:\\s*(.+?)\\s*$", re.IGNORECASE),
}


def _normalize_issues(raw_value: str, continuation_lines: list[str]) -> tuple[str, ...]:
    candidates: list[str] = []
    if raw_value and raw_value.lower() not in {"none", "n/a"}:
        candidates.append(raw_value)
    for line in continuation_lines:
        item = re.sub(r"^\\s*[-*]\\s*", "", line).strip()
        if item:
            candidates.append(item)
    return tuple(candidates)


def parse_review(raw_review: str) -> dict[str, object]:
    for marker in SELF_REVIEW_MARKERS:
        if marker.search(raw_review):
            raise ValueError("Review artifact appears to be a self-review, not a Codex review.")

    captured: dict[str, str] = {}
    continuations: dict[str, list[str]] = {"blocking_issues": [], "non_blocking_issues": []}
    active_multiline_field: str | None = None

    for line in raw_review.splitlines():
        matched_field = None
        for field_name, pattern in FIELD_PATTERNS.items():
            match = pattern.match(line)
            if match:
                captured[field_name] = match.group(1).strip()
                active_multiline_field = field_name if field_name in continuations else None
                matched_field = field_name
                break
        if matched_field is not None:
            continue
        if active_multiline_field and line.strip():
            continuations[active_multiline_field].append(line)

    required_fields = {
        "verdict",
        "current_unit_status",
        "blocking_issues",
        "non_blocking_issues",
        "cause_classification",
        "delivery_proof_status",
        "next_bounded_unit_may_start",
        "suggested_next_action",
    }
    missing_fields = sorted(required_fields - captured.keys())
    if missing_fields:
        raise ValueError("Review output missing required fields: " + ", ".join(missing_fields))

    verdict = captured["verdict"].upper()
    current_unit_status = captured["current_unit_status"].upper()
    cause_classification = captured["cause_classification"].upper()
    delivery_proof_status = captured["delivery_proof_status"].upper()
    next_bounded_unit_may_start = captured["next_bounded_unit_may_start"].upper()

    if verdict not in VALID_VERDICTS:
        raise ValueError(f"Invalid review verdict: {captured['verdict']}")
    if current_unit_status not in VALID_STATUSES:
        raise ValueError(f"Invalid current unit status: {captured['current_unit_status']}")
    if cause_classification not in VALID_CAUSES:
        raise ValueError(f"Invalid cause classification: {captured['cause_classification']}")
    if delivery_proof_status not in VALID_DELIVERY:
        raise ValueError(f"Invalid delivery proof status: {captured['delivery_proof_status']}")
    if next_bounded_unit_may_start not in VALID_PROGRESS:
        raise ValueError(
            "Invalid next bounded unit may start value: " + captured["next_bounded_unit_may_start"]
        )

    suggested_next_action = captured["suggested_next_action"].strip()
    if not suggested_next_action:
        raise ValueError("Suggested next action must not be empty.")

    return {
        "verdict": verdict,
        "current_unit_status": current_unit_status,
        "blocking_issues": _normalize_issues(captured["blocking_issues"], continuations["blocking_issues"]),
        "non_blocking_issues": _normalize_issues(
            captured["non_blocking_issues"], continuations["non_blocking_issues"]
        ),
        "cause_classification": cause_classification,
        "delivery_proof_status": delivery_proof_status,
        "next_bounded_unit_may_start": next_bounded_unit_may_start,
        "suggested_next_action": suggested_next_action,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a saved dual-agent review artifact.")
    parser.add_argument("--review-file", type=Path, required=True, help="Path to the saved review artifact.")
    parser.add_argument(
        "--mode",
        choices=("generic", "lead", "final"),
        default="generic",
        help="Review gate mode.",
    )
    parser.add_argument(
        "--require-delivery-proof",
        choices=tuple(sorted(VALID_DELIVERY)),
        help="Require a specific delivery proof status.",
    )
    args = parser.parse_args()

    if not args.review_file.exists():
        print(f"ERROR: review artifact not found: {args.review_file}", file=sys.stderr)
        return 1

    try:
        review = parse_review(args.review_file.read_text())
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if review["blocking_issues"]:
        print("ERROR: review artifact still lists blocking issues.", file=sys.stderr)
        return 1

    if args.mode in {"lead", "final"}:
        if review["verdict"] != "APPROVED":
            print("ERROR: review artifact is not approved.", file=sys.stderr)
            return 1
        if review["next_bounded_unit_may_start"] != "YES":
            print("ERROR: reviewer did not authorize progression.", file=sys.stderr)
            return 1

    if args.mode == "final" and review["current_unit_status"] not in {"PASS", "PASS_WITH_EXCEPTION"}:
        print("ERROR: final review artifact does not certify a passing unit state.", file=sys.stderr)
        return 1

    if args.require_delivery_proof and review["delivery_proof_status"] != args.require_delivery_proof:
        print(
            "ERROR: review artifact delivery proof status is "
            f"{review['delivery_proof_status']}, expected {args.require_delivery_proof}.",
            file=sys.stderr,
        )
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def build_stop_monitor_script() -> str:
    source = Path(stop_monitor_module.__file__).read_text()
    if source.startswith("#!/usr/bin/env python3\n"):
        return source
    return "#!/usr/bin/env python3\n" + source


def default_workflow_config() -> WorkflowConfig:
    glm_provider = ProviderConfig(
        name="glm",
        model="glm-5.1",
        base_url="https://api.z.ai/api/coding/paas/v4/",
        api_key_env="GLM_API_KEY",
    )
    return WorkflowConfig(
        builder=AgentConfig(
            name="glm-builder",
            provider=glm_provider,
            role="builder",
            can_edit=True,
            prompt="Implement requested changes and self-review before handoff.",
        ),
        reviewer=ReviewerConfig(
            prompt="Review diffs and call out blocking and non-blocking issues. Only edit when explicitly requested by the user.",
        ),
        delivery_verification_commands=[
            "git status --short",
            "git rev-parse --abbrev-ref HEAD",
            "git log <target-branch> -1 --oneline",
            "git log HEAD -1 --oneline",
            "gh api repos/<owner>/<repo>/contents/<artifact-path>",
            "gh run view <run-id> --repo <owner>/<repo> --json headSha,headBranch,conclusion",
        ],
        delivery_principles=[
            "Treat local completion and remote delivery as different states.",
            "Do not claim success for a remote target unless the exact artifact exists there.",
            "Do not treat workflow success as proof unless the run is bound to the intended artifact state.",
            "If the working tree contains unrelated work, isolate delivery changes before publishing.",
            "If evidence conflicts, stop and classify the unit as STALLED or CHANGES_REQUIRED.",
        ],
        forum_adjudication_enabled=True,
        premium_review_optimize_enabled=True,
    )


def _export_assets(output_dir: Path) -> None:
    config = default_workflow_config()
    opencode_dir = output_dir / ".opencode"
    agents_dir = opencode_dir / "agents"
    commands_dir = opencode_dir / "commands"
    prompts_dir = output_dir / ".dual-agents"

    for relative_path in TRANSIENT_OPCODE_PATHS:
        transient_path = output_dir / relative_path
        if transient_path.is_dir():
            shutil.rmtree(transient_path)
        elif transient_path.exists():
            transient_path.unlink()

    agents_dir.mkdir(parents=True, exist_ok=True)
    commands_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    (opencode_dir / ".gitignore").write_text("node_modules\npackage.json\nbun.lock\n")
    (opencode_dir / "opencode.json").write_text(build_opencode_config(config))
    (commands_dir / "dual.md").write_text(build_command_markdown(config))
    for filename, content in build_agent_markdown(config).items():
        (agents_dir / filename).write_text(content)
    (prompts_dir / "codex-review.txt").write_text(build_review_prompt(config) + "\n")
    (prompts_dir / "validate_report.py").write_text(build_report_validator_script())
    (prompts_dir / "validate_review.py").write_text(build_review_validator_script())
    (prompts_dir / "monitor_stop.py").write_text(build_stop_monitor_script())


def _artifact_filename_for_mode(mode: ReviewGateMode) -> str:
    if mode == ReviewGateMode.LEAD:
        return "lead-review.txt"
    if mode == ReviewGateMode.FINAL:
        return "final-review.txt"
    raise ValueError(f"Unsupported review gate mode for artifact persistence: {mode.value}")


def _invalid_artifact_path(artifact_path: Path) -> Path:
    return artifact_path.with_name(f"{artifact_path.stem}.invalid{artifact_path.suffix}")


def _run_codex_review(*, config: WorkflowConfig, review_request: str, cwd: Path) -> str:
    prompt = build_review_prompt(config) + "\n\n" + review_request.strip() + "\n"
    command = [*config.reviewer.command, prompt]
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "codex review command failed."
        raise typer.BadParameter(f"Codex review failed: {stderr}")
    output = result.stdout.strip()
    if not output:
        raise typer.BadParameter("Codex review returned empty output.")
    return output


def _normalize_review_request(review_request: str, *, mode: ReviewGateMode) -> str:
    normalized = review_request.strip()
    if mode == ReviewGateMode.LEAD:
        preamble = (
            "REVIEW MODE: LEAD\n"
            "This is a PRE-IMPLEMENTATION design gate for exactly one bounded unit.\n"
            "The unit is expected to be not yet implemented.\n"
            "Judge whether the proposed implementation plan is concrete and safe to start.\n"
            "Do not request completed code, test results, or a passing diff merely because implementation has not begun.\n"
        )
        return preamble + "\n" + normalized
    if mode == ReviewGateMode.FINAL:
        preamble = (
            "REVIEW MODE: FINAL\n"
            "This is a POST-IMPLEMENTATION critical review for exactly one bounded unit.\n"
            "Judge the produced code, evidence, and verification results for that unit.\n"
        )
        return preamble + "\n" + normalized
    return normalized


def _load_controller_from_state(
    *,
    repo_root: Path,
    delivery_sensitive: bool,
) -> tuple[WorkflowController, RunState, Path]:
    reviews_root = repo_root / ".dual-agents" / "reviews"
    state_path = default_state_path(repo_root)
    run_state = load_run_state(state_path)
    controller = WorkflowController(
        delivery_sensitive=delivery_sensitive,
        reviews_root=reviews_root,
    )
    apply_run_state(controller, run_state)
    return controller, run_state, state_path


def _normalize_unit_key(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"\.md$", "", lowered)
    lowered = re.sub(r"^\d+[a-z]?-", "", lowered)
    lowered = re.sub(r"^task-\d+-", "", lowered)
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-+", "-", lowered).strip("-")
    return lowered


def _discover_task_file(repo_root: Path, unit_slug: str) -> Path | None:
    epic_root = repo_root / "epic"
    if not epic_root.exists():
        return None

    target_key = _normalize_unit_key(unit_slug)
    matches: list[Path] = []
    for path in epic_root.rglob("*.md"):
        candidate_key = _normalize_unit_key(path.stem)
        if candidate_key == target_key or candidate_key.endswith(target_key) or target_key.endswith(candidate_key):
            matches.append(path)

    if len(matches) == 1:
        return matches[0]
    return None


def _validate_saved_final_review(
    review_path: Path,
    *,
    require_delivery_proof: DeliveryProofStatus | None = None,
) -> dict[str, str]:
    raw_review = review_path.read_text()
    review_result = parse_review_result(raw_review)
    validate_review_result(
        review_result,
        mode=ReviewGateMode.FINAL,
        require_delivery_proof=require_delivery_proof,
    )
    return {
        "unit_slug": review_path.parent.name,
        "artifact_path": str(review_path),
        "current_unit_status": review_result.current_unit_status.value,
        "next_bounded_unit_may_start": review_result.next_bounded_unit_may_start.value,
    }


def _submit_existing_review_artifact(
    *,
    unit_slug: str,
    mode: ReviewGateMode,
    review_file: Path,
    repo_root: Path,
    delivery_sensitive: bool,
    require_delivery_proof: DeliveryProofStatus | None,
) -> dict[str, str]:
    if mode == ReviewGateMode.GENERIC:
        raise typer.BadParameter("submit-review-artifact only supports lead or final modes.")

    controller, run_state, state_path = _load_controller_from_state(
        repo_root=repo_root,
        delivery_sensitive=delivery_sensitive,
    )
    if mode == ReviewGateMode.LEAD:
        controller.begin_new_bounded_unit(unit_slug)
        controller.stage = WorkflowStage.EPIC_REVIEW
    else:
        if run_state.current_unit and run_state.current_unit.unit_slug != unit_slug:
            raise typer.BadParameter(
                f"Run-state current unit is {run_state.current_unit.unit_slug}, not {unit_slug}."
            )
        controller.current_unit_slug = unit_slug.strip()
        controller.stage = WorkflowStage.CRITICAL_REVIEW

    artifact_path = controller.expected_review_artifact_path()
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    if review_file.resolve() != artifact_path.resolve():
        artifact_path.write_text(review_file.read_text().rstrip() + "\n")

    review_result = parse_review_result(artifact_path.read_text())
    validate_review_result(
        review_result,
        mode=mode,
        require_delivery_proof=require_delivery_proof,
    )
    controller.submit_saved_review()
    run_state.current_unit = build_bounded_unit_state(controller)
    run_state.current_unit = mark_progress(
        run_state.current_unit,
        open_blocking_issues=list(review_result.blocking_issues),
    )
    save_run_state(state_path, run_state)
    return {
        "unit_slug": unit_slug,
        "mode": mode.value,
        "artifact_path": str(artifact_path),
        "state_path": str(state_path),
        "stage": controller.stage.value,
        "current_unit_status": review_result.current_unit_status.value,
        "next_bounded_unit_may_start": review_result.next_bounded_unit_may_start.value,
        "suggested_next_action": review_result.suggested_next_action,
    }


@app.callback()
def app_callback() -> None:
    """Dual-agent workflow helpers."""


@app.command("preview")
def preview_assets() -> None:
    config = default_workflow_config()
    payload = {
        "opencode_config": build_opencode_config(config),
        "command": build_command_markdown(config),
        "agents": build_agent_markdown(config),
        "codex_review_prompt": build_review_prompt(config),
        "codex_review_command": build_review_command(config),
    }
    typer.echo(json.dumps(payload, indent=2))


@app.command("explain-stop")
def explain_stop(
    transcript_file: Path = typer.Option(..., exists=True, dir_okay=False, readable=True),
    unit_name: str = typer.Option("current unit"),
) -> None:
    signal = classify_stop(transcript_file.read_text())
    typer.echo(format_stop_report(signal, unit_name=unit_name))


@app.command("export")
def export_assets(output_dir: Path = typer.Option(..., dir_okay=True, file_okay=False, writable=True)) -> None:
    _export_assets(output_dir)
    typer.echo(f"Exported dual-agent assets to {output_dir}")


@app.command("doctor")
def doctor() -> None:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("python>=3.12", sys.version_info >= (3, 12), sys.version.split()[0]))
    checks.append(("GLM_API_KEY", bool(os.getenv("GLM_API_KEY")), "set" if os.getenv("GLM_API_KEY") else "missing"))
    checks.append(("opencode", shutil.which("opencode") is not None, shutil.which("opencode") or "not found"))
    checks.append(("codex", shutil.which("codex") is not None, shutil.which("codex") or "not found"))

    all_ok = True
    for name, ok, detail in checks:
        status = "OK" if ok else "MISSING"
        typer.echo(f"{status:7} {name}: {detail}")
        all_ok = all_ok and ok

    if not all_ok:
        raise typer.Exit(code=1)


@app.command("init-target")
def init_target(
    output_dir: Path = typer.Option(..., dir_okay=True, file_okay=False, writable=True),
    doctor_check: bool = typer.Option(True, help="Run environment checks before exporting."),
) -> None:
    if doctor_check:
        missing = []
        if sys.version_info < (3, 12):
            missing.append("python>=3.12")
        if not os.getenv("GLM_API_KEY"):
            missing.append("GLM_API_KEY")
        if shutil.which("opencode") is None:
            missing.append("opencode")
        if shutil.which("codex") is None:
            missing.append("codex")
        if missing:
            typer.echo("Environment is not ready. Run `dual-agents doctor` and fix:", err=True)
            for item in missing:
                typer.echo(f"- {item}", err=True)
            raise typer.Exit(code=1)

    _export_assets(output_dir)
    typer.echo(f"Initialized dual-agent assets in {output_dir}")
    typer.echo("Next steps:")
    typer.echo("1. Start a fresh OpenCode session in the target repo.")
    typer.echo("2. Commit .opencode/ and .dual-agents/ in the target repo.")
    typer.echo("3. Use `/dual` or the configured trigger phrase in that repo.")


@app.command("start-unit")
def start_unit(
    unit_slug: str = typer.Option(..., help="Bounded unit slug, e.g. task-01-query-map."),
    repo_root: Path = typer.Option(Path("."), dir_okay=True, file_okay=False, resolve_path=True, help="Target repo root."),
    delivery_sensitive: bool = typer.Option(False, help="Require delivery-sensitive handling for this unit."),
    start_mode: BoundedUnitStartMode = typer.Option(
        BoundedUnitStartMode.AUTO,
        case_sensitive=False,
        help="How to start the bounded unit: auto, implementation, or review.",
    ),
    task_summary: str | None = typer.Option(
        None,
        help="Optional bounded task summary used when auto-selecting the start mode.",
    ),
    task_file: Path | None = typer.Option(
        None,
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Optional task spec file used when auto-selecting the start mode.",
    ),
) -> None:
    repo_root = repo_root.resolve()
    controller, run_state, state_path = _load_controller_from_state(
        repo_root=repo_root,
        delivery_sensitive=delivery_sensitive,
    )
    controller.begin_new_bounded_unit(unit_slug)
    resolved_task_file = task_file or _discover_task_file(repo_root, unit_slug)
    task_context = resolved_task_file.read_text() if resolved_task_file is not None else None
    controller.stage = choose_initial_stage(
        start_mode=start_mode,
        task_summary=task_summary,
        task_context=task_context,
    )
    run_state.current_unit = build_bounded_unit_state(controller)
    save_run_state(state_path, run_state)
    typer.echo(
        json.dumps(
            {
                "unit_slug": unit_slug,
                "stage": controller.stage.value,
                "start_mode": start_mode.value,
                "task_file": str(resolved_task_file) if resolved_task_file is not None else None,
                "state_path": str(state_path),
                "expected_lead_review_path": run_state.current_unit.expected_lead_review_path,
                "expected_final_review_path": run_state.current_unit.expected_final_review_path,
            },
            indent=2,
        )
    )


@app.command("review-gate")
def review_gate(
    unit_slug: str = typer.Option(..., help="Bounded unit slug, e.g. task-01-query-map."),
    mode: ReviewGateMode = typer.Option(..., case_sensitive=False, help="Review gate mode: lead or final."),
    request_file: Path = typer.Option(..., exists=True, dir_okay=False, readable=True, help="File containing the bounded review request packet."),
    repo_root: Path = typer.Option(Path("."), dir_okay=True, file_okay=False, resolve_path=True, help="Target repo root."),
    delivery_sensitive: bool = typer.Option(False, help="Require delivery-sensitive final review handling."),
    require_delivery_proof: DeliveryProofStatus | None = typer.Option(None, case_sensitive=False, help="Require specific delivery proof status for final reviews."),
) -> None:
    if mode == ReviewGateMode.GENERIC:
        raise typer.BadParameter("review-gate only supports lead or final modes.")

    config = default_workflow_config()
    repo_root = repo_root.resolve()
    review_request = request_file.read_text().strip()
    if not review_request:
        raise typer.BadParameter("Review request file must not be empty.")
    review_request = _normalize_review_request(review_request, mode=mode)

    controller, run_state, state_path = _load_controller_from_state(
        repo_root=repo_root,
        delivery_sensitive=delivery_sensitive,
    )
    if mode == ReviewGateMode.LEAD:
        controller.begin_new_bounded_unit(unit_slug)
        controller.stage = WorkflowStage.EPIC_REVIEW
    else:
        if run_state.current_unit and run_state.current_unit.unit_slug != unit_slug:
            raise typer.BadParameter(
                f"Run-state current unit is {run_state.current_unit.unit_slug}, not {unit_slug}."
            )
        controller.current_unit_slug = unit_slug.strip()
        controller.stage = WorkflowStage.CRITICAL_REVIEW

    artifact_path = controller.expected_review_artifact_path()
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    review_output = _run_codex_review(config=config, review_request=review_request, cwd=repo_root)
    try:
        review_result = parse_review_result(review_output)
    except WorkflowViolation as exc:
        invalid_path = _invalid_artifact_path(artifact_path)
        invalid_path.write_text(review_output + "\n")
        raise typer.BadParameter(
            f"Codex review returned invalid structured output: {exc}. Raw output saved to {invalid_path}."
        ) from exc

    artifact_path.write_text(review_output + "\n")
    validate_review_result(
        review_result,
        mode=mode,
        require_delivery_proof=require_delivery_proof,
    )
    controller.submit_saved_review()
    run_state.current_unit = build_bounded_unit_state(controller)
    run_state.current_unit = mark_progress(
        run_state.current_unit,
        open_blocking_issues=list(review_result.blocking_issues),
    )
    save_run_state(state_path, run_state)

    typer.echo(
        json.dumps(
            {
                "unit_slug": unit_slug,
                "mode": mode.value,
                "artifact_path": str(artifact_path),
                "state_path": str(state_path),
                "stage": controller.stage.value,
                "current_unit_status": review_result.current_unit_status.value,
                "next_bounded_unit_may_start": review_result.next_bounded_unit_may_start.value,
                "suggested_next_action": review_result.suggested_next_action,
            },
            indent=2,
        )
    )


@app.command("submit-review-artifact")
def submit_review_artifact(
    unit_slug: str = typer.Option(..., help="Bounded unit slug, e.g. task-01-query-map."),
    mode: ReviewGateMode = typer.Option(..., case_sensitive=False, help="Review gate mode: lead or final."),
    review_file: Path = typer.Option(..., exists=True, dir_okay=False, readable=True, resolve_path=True, help="Existing saved review artifact to submit."),
    repo_root: Path = typer.Option(Path("."), dir_okay=True, file_okay=False, resolve_path=True, help="Target repo root."),
    delivery_sensitive: bool = typer.Option(False, help="Require delivery-sensitive final review handling."),
    require_delivery_proof: DeliveryProofStatus | None = typer.Option(None, case_sensitive=False, help="Require specific delivery proof status for final reviews."),
) -> None:
    repo_root = repo_root.resolve()
    payload = _submit_existing_review_artifact(
        unit_slug=unit_slug,
        mode=mode,
        review_file=review_file,
        repo_root=repo_root,
        delivery_sensitive=delivery_sensitive,
        require_delivery_proof=require_delivery_proof,
    )
    typer.echo(json.dumps(payload, indent=2))


@app.command("pre-completion-audit")
def pre_completion_audit(
    repo_root: Path = typer.Option(Path("."), dir_okay=True, file_okay=False, resolve_path=True, help="Target repo root."),
    require_delivery_proof: DeliveryProofStatus | None = typer.Option(None, case_sensitive=False, help="Require specific delivery proof status for audited final reviews."),
) -> None:
    repo_root = repo_root.resolve()
    reviews_root = repo_root / ".dual-agents" / "reviews"
    state_path = default_state_path(repo_root)
    run_state = load_run_state(state_path)

    failures: list[dict[str, str]] = []
    audited: list[dict[str, str]] = []

    final_review_paths = sorted(reviews_root.glob("*/final-review.txt"))
    for review_path in final_review_paths:
        try:
            audited.append(
                _validate_saved_final_review(
                    review_path,
                    require_delivery_proof=require_delivery_proof,
                )
            )
        except Exception as exc:
            failures.append(
                {
                    "unit_slug": review_path.parent.name,
                    "artifact_path": str(review_path),
                    "error": str(exc),
                }
            )

    if run_state.current_unit is not None:
        expected_final = Path(run_state.current_unit.expected_final_review_path)
        if not expected_final.exists():
            failures.append(
                {
                    "unit_slug": run_state.current_unit.unit_slug,
                    "artifact_path": str(expected_final),
                    "error": "Current run-state unit is missing final-review.txt.",
                }
            )
        elif not any(item["artifact_path"] == str(expected_final) for item in audited):
            try:
                audited.append(
                    _validate_saved_final_review(
                        expected_final,
                        require_delivery_proof=require_delivery_proof,
                    )
                )
            except Exception as exc:
                failures.append(
                    {
                        "unit_slug": run_state.current_unit.unit_slug,
                        "artifact_path": str(expected_final),
                        "error": str(exc),
                    }
                )

    if not audited:
        failures.append(
            {
                "unit_slug": "",
                "artifact_path": str(reviews_root),
                "error": "No final review artifacts found to audit.",
            }
        )

    payload = {
        "repo_root": str(repo_root),
        "state_path": str(state_path),
        "audited_units": audited,
        "failures": failures,
    }
    typer.echo(json.dumps(payload, indent=2))
    if failures:
        raise typer.Exit(code=1)


@app.command("heartbeat")
def heartbeat(
    unit_slug: str = typer.Option(..., help="Bounded unit slug that should already be active."),
    repo_root: Path = typer.Option(Path("."), dir_okay=True, file_okay=False, resolve_path=True, help="Target repo root."),
    note: str | None = typer.Option(None, help="Short note explaining why the unit is still active."),
) -> None:
    repo_root = repo_root.resolve()
    run_state = load_run_state(default_state_path(repo_root))
    if run_state.current_unit is None:
        raise typer.BadParameter("No active bounded unit in run-state.")
    if run_state.current_unit.unit_slug != unit_slug:
        raise typer.BadParameter(f"Run-state current unit is {run_state.current_unit.unit_slug}, not {unit_slug}.")

    run_state.current_unit = mark_heartbeat(run_state.current_unit, note=note)
    save_run_state(default_state_path(repo_root), run_state)
    typer.echo(
        json.dumps(
            {
                "unit_slug": unit_slug,
                "stage": run_state.current_unit.stage.value,
                "state_path": str(default_state_path(repo_root)),
                "last_heartbeat_at": run_state.current_unit.last_heartbeat_at,
                "note": run_state.current_unit.last_watchdog_warning,
            },
            indent=2,
        )
    )


@app.command("watchdog-check")
def watchdog_check(
    repo_root: Path = typer.Option(Path("."), dir_okay=True, file_okay=False, resolve_path=True, help="Target repo root."),
) -> None:
    repo_root = repo_root.resolve()
    state_path = default_state_path(repo_root)
    run_state = load_run_state(state_path)
    decision = evaluate_watchdog(run_state)

    if run_state.current_unit is not None:
        if decision.status == WatchdogStatus.WARN:
            run_state.current_unit = run_state.current_unit.model_copy(
                update={"last_watchdog_warning": decision.reason}
            )
            save_run_state(state_path, run_state)
        elif decision.status == WatchdogStatus.STALLED:
            run_state.current_unit = mark_stalled(run_state.current_unit, reason=decision.reason)
            save_run_state(state_path, run_state)

    typer.echo(
        json.dumps(
            {
                "status": decision.status.value,
                "reason": decision.reason,
                "idle_seconds": decision.idle_seconds,
                "expected_artifacts_missing": list(decision.expected_artifacts_missing),
                "next_action": decision.next_action,
                "state_path": str(state_path),
            },
            indent=2,
        )
    )


@app.command("stop-unit")
def stop_unit(
    unit_slug: str = typer.Option(..., help="Bounded unit slug that should be stopped."),
    repo_root: Path = typer.Option(Path("."), dir_okay=True, file_okay=False, resolve_path=True, help="Target repo root."),
    reason: str = typer.Option(..., help="Why the bounded unit is being stopped."),
) -> None:
    repo_root = repo_root.resolve()
    state_path = default_state_path(repo_root)
    run_state = load_run_state(state_path)
    if run_state.current_unit is None:
        raise typer.BadParameter("No active bounded unit in run-state.")
    if run_state.current_unit.unit_slug != unit_slug:
        raise typer.BadParameter(f"Run-state current unit is {run_state.current_unit.unit_slug}, not {unit_slug}.")

    run_state.current_unit = mark_stalled(run_state.current_unit, reason=reason)
    save_run_state(state_path, run_state)
    typer.echo(
        json.dumps(
            {
                "unit_slug": unit_slug,
                "stage": run_state.current_unit.stage.value,
                "last_stop_reason": run_state.current_unit.last_stop_reason,
                "state_path": str(state_path),
            },
            indent=2,
        )
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
