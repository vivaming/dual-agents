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
from dual_agents.stop_monitor import classify_stop, format_stop_report

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


def build_stop_monitor_script() -> str:
    return """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path


class StopCategory(str, Enum):
    STREAM_TIMEOUT = "STREAM_TIMEOUT"
    TOOL_SCHEMA_ERROR = "TOOL_SCHEMA_ERROR"
    OUTPUT_CORRUPTION = "OUTPUT_CORRUPTION"
    DATA_SHAPE_MISMATCH = "DATA_SHAPE_MISMATCH"
    CAPABILITY_MISMATCH = "CAPABILITY_MISMATCH"
    SESSION_DEGRADATION = "SESSION_DEGRADATION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class StopSignal:
    category: StopCategory
    evidence: tuple[str, ...]
    recovery: str
    requires_fresh_session: bool
    matched_categories: tuple[StopCategory, ...]


STOP_PATTERN_MAP = {
    StopCategory.STREAM_TIMEOUT: (
        re.compile(r"SSE read timed out", re.IGNORECASE),
        re.compile(r"review times? out", re.IGNORECASE),
    ),
    StopCategory.TOOL_SCHEMA_ERROR: (
        re.compile(r"invalid arguments", re.IGNORECASE),
        re.compile(r"expected string, received undefined", re.IGNORECASE),
        re.compile(r"subagent_type", re.IGNORECASE),
        re.compile(r"unknown runtime schema", re.IGNORECASE),
    ),
    StopCategory.OUTPUT_CORRUPTION: (
        re.compile(r"^\\s*Thinking:", re.IGNORECASE | re.MULTILINE),
        re.compile(r"<(?:parameter|invoke|system)\\b", re.IGNORECASE),
        re.compile(r"zsh:1: unmatched", re.IGNORECASE),
        re.compile(r"\\}\\s*else\\s*,\\}", re.IGNORECASE),
    ),
    StopCategory.DATA_SHAPE_MISMATCH: (
        re.compile(r"AttributeError: 'str' object has no attribute 'get'", re.IGNORECASE),
        re.compile(r"Traceback \\(most recent call last\\):", re.IGNORECASE),
    ),
    StopCategory.CAPABILITY_MISMATCH: (
        re.compile(r"can't view images", re.IGNORECASE),
        re.compile(r"don't have multimodal", re.IGNORECASE),
        re.compile(r"browser or app may not be secure", re.IGNORECASE),
        re.compile(r"couldn't sign you in", re.IGNORECASE),
    ),
}


def _extract_evidence(text: str, patterns):
    evidence = []
    for line in text.splitlines():
        if any(pattern.search(line) for pattern in patterns):
            stripped = line.strip()
            if stripped:
                evidence.append(stripped)
    return tuple(dict.fromkeys(evidence))


def _recovery_for(category: StopCategory):
    recovery_map = {
        StopCategory.STREAM_TIMEOUT: (
            "Save a bounded checkpoint, restart in a fresh session, and retry only the smallest unresolved unit.",
            True,
        ),
        StopCategory.TOOL_SCHEMA_ERROR: (
            "Stop speculative subagent/tool retries, record the missing runtime field, and either use a known-good path or restart fresh.",
            True,
        ),
        StopCategory.OUTPUT_CORRUPTION: (
            "Discard the malformed output, save a concise stop report, and continue in a fresh session with a bounded next action.",
            True,
        ),
        StopCategory.DATA_SHAPE_MISMATCH: (
            "Inspect the real data shape first, then rerun the bounded analysis with a parser that matches the artifact schema.",
            False,
        ),
        StopCategory.CAPABILITY_MISMATCH: (
            "Use a capability that the current runtime actually supports, or switch to a manual or alternate path without looping.",
            False,
        ),
        StopCategory.SESSION_DEGRADATION: (
            "Stop the current session, save a stop report with evidence, and resume from a fresh session with one bounded next step.",
            True,
        ),
        StopCategory.UNKNOWN: (
            "Capture the transcript snippet and classify it manually before retrying.",
            False,
        ),
    }
    return recovery_map[category]


def classify_stop(raw_text: str) -> StopSignal:
    text = raw_text.strip()
    if not text:
        recovery, fresh = _recovery_for(StopCategory.UNKNOWN)
        return StopSignal(StopCategory.UNKNOWN, (), recovery, fresh, ())

    matched = []
    evidence = []
    for category, patterns in STOP_PATTERN_MAP.items():
        category_evidence = _extract_evidence(text, patterns)
        if category_evidence:
            matched.append(category)
            evidence.extend(category_evidence)

    unique_matched = tuple(dict.fromkeys(matched))
    if len(unique_matched) >= 2 or text.lower().count("invalid arguments") >= 2:
        recovery, fresh = _recovery_for(StopCategory.SESSION_DEGRADATION)
        return StopSignal(
            StopCategory.SESSION_DEGRADATION,
            tuple(dict.fromkeys(evidence)),
            recovery,
            fresh,
            unique_matched,
        )

    category = unique_matched[0] if unique_matched else StopCategory.UNKNOWN
    recovery, fresh = _recovery_for(category)
    return StopSignal(category, tuple(dict.fromkeys(evidence)), recovery, fresh, unique_matched)


def format_stop_report(signal: StopSignal, unit_name: str):
    evidence_lines = "\\n".join(f"- {item}" for item in signal.evidence[:4]) or "- none captured"
    matched = ", ".join(category.value for category in signal.matched_categories) or signal.category.value
    return (
        f"Current unit: {unit_name}\\n"
        f"Stop signal: {signal.category.value}\\n"
        f"Matched categories: {matched}\\n"
        "Evidence:\\n"
        f"{evidence_lines}\\n"
        f"Next recovery step: {signal.recovery}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify a dual-agent stop transcript.")
    parser.add_argument("--transcript-file", type=Path, help="Path to transcript file.")
    parser.add_argument("--unit-name", default="current unit", help="Bounded unit name.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of the formatted report.")
    args = parser.parse_args()

    text = args.transcript_file.read_text() if args.transcript_file else sys.stdin.read()
    signal = classify_stop(text)
    if args.json:
        payload = asdict(signal)
        payload["category"] = signal.category.value
        payload["matched_categories"] = [category.value for category in signal.matched_categories]
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(format_stop_report(signal, args.unit_name))
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
    (prompts_dir / "monitor_stop.py").write_text(build_stop_monitor_script())


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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
