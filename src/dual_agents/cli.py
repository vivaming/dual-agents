from __future__ import annotations

import json
from pathlib import Path

import typer

from dual_agents.codex_review import build_review_command, build_review_prompt
from dual_agents.config import AgentConfig, ProviderConfig, ReviewerConfig, WorkflowConfig
from dual_agents.opencode_assets import build_agent_markdown, build_command_markdown, build_opencode_config

app = typer.Typer(help="CLI for the dual-agent workflow.", no_args_is_help=True)


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
        choices=("summary", "post-review"),
        default="summary",
        help="Validation mode.",
    )
    parser.add_argument("--report-file", type=Path, help="Path to a file containing the report text.")
    parser.add_argument("--require-term", action="append", default=[], help="Term that must appear in the report.")
    parser.add_argument("--max-issues", type=int, default=3, help="Maximum issue bullets for post-review mode.")
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

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def default_workflow_config() -> WorkflowConfig:
    glm_provider = ProviderConfig(
        name="glm",
        model="glm-5",
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
    )


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
    config = default_workflow_config()
    opencode_dir = output_dir / ".opencode"
    agents_dir = opencode_dir / "agents"
    commands_dir = opencode_dir / "commands"
    prompts_dir = output_dir / ".dual-agents"

    agents_dir.mkdir(parents=True, exist_ok=True)
    commands_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    (opencode_dir / "opencode.json").write_text(build_opencode_config(config))
    (commands_dir / "dual.md").write_text(build_command_markdown(config))
    for filename, content in build_agent_markdown(config).items():
        (agents_dir / filename).write_text(content)
    (prompts_dir / "codex-review.txt").write_text(build_review_prompt(config) + "\n")
    (prompts_dir / "validate_report.py").write_text(build_report_validator_script())

    typer.echo(f"Exported dual-agent assets to {output_dir}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
