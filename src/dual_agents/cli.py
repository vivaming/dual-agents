from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import typer

from dual_agents.codex_review import build_review_command, build_review_prompt
from dual_agents.config import AgentConfig, ProviderConfig, ReviewerConfig, WorkflowConfig
from dual_agents.opencode_assets import build_agent_markdown, build_command_markdown, build_opencode_config

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

FIELD_PATTERNS = {
    "verdict": re.compile(r"^\\s*(?:\\d+\\.\\s*)?Verdict:\\s*(.+?)\\s*$", re.IGNORECASE),
    "current_unit_status": re.compile(r"^\\s*(?:\\d+\\.\\s*)?Current unit status:\\s*(.+?)\\s*$", re.IGNORECASE),
    "blocking_issues": re.compile(r"^\\s*(?:\\d+\\.\\s*)?Blocking issues:\\s*(.*?)\\s*$", re.IGNORECASE),
    "non_blocking_issues": re.compile(r"^\\s*(?:\\d+\\.\\s*)?Non-blocking issues:\\s*(.*?)\\s*$", re.IGNORECASE),
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


def default_workflow_config() -> WorkflowConfig:
    glm_provider = ProviderConfig(
        name="glm",
        model="glm-4-turbo",
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
