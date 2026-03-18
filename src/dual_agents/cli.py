from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import typer

from dual_agents.codex_review import build_review_command, build_review_prompt
from dual_agents.completeness_analyzer import (
    CompletenessAnalyzerError,
    analyze_brand_sets,
    format_text_report,
    supported_schema_description,
)
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
        re.compile(r"SyntaxError:", re.IGNORECASE),
        re.compile(r"JSONDecodeError:", re.IGNORECASE),
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
            "Inspect schema, fix parser, and rerun the same bounded analysis.",
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


def build_completeness_analyzer_script() -> str:
    return """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

CRITICAL_FIELDS = (
    "motor_power_watts",
    "battery_wh",
    "weight_lbs",
    "max_speed_mph",
)

BRAND_SETS = {
    "affiliate": (
        "kingbull",
        "puckipuppy",
        "vivi",
        "vanpowers",
        "lacros",
        "tenways",
        "megawheels",
    ),
    "official": (
        "radpower",
        "ride1up",
        "super73",
        "aventon",
        "velotric",
    ),
}

SUPPORTED_INPUT_PATTERN = "data/<brand>/coverage_report.json"


class CompletenessAnalyzerError(ValueError):
    pass


@dataclass(frozen=True)
class BrandCompleteness:
    brand: str
    brand_type: str
    models_attempted: int
    models_succeeded: int
    critical_coverage: dict[str, float]
    average_critical_coverage: float


def supported_schema_description() -> str:
    return (
        "Supported inputs:\\n"
        f"- {SUPPORTED_INPUT_PATTERN}\\n"
        "Required top-level keys in each coverage report:\\n"
        "- brand: string\\n"
        "- products_attempted: integer\\n"
        "- products_succeeded: integer\\n"
        "- fields: object\\n"
        "Required per-field schema for critical fields:\\n"
        "- normalized_success: integer\\n"
    )


def _require_dict(payload: object, *, context: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise CompletenessAnalyzerError(f"{context} must be an object.")
    return payload


def _require_int(payload: dict[str, object], key: str, *, context: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CompletenessAnalyzerError(f"{context}.{key} must be an integer.")
    return value


def _require_string(payload: dict[str, object], key: str, *, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CompletenessAnalyzerError(f"{context}.{key} must be a non-empty string.")
    return value.strip()


def _load_json(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise CompletenessAnalyzerError(f"Missing required coverage report: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CompletenessAnalyzerError(f"Invalid JSON in {path}: {exc}") from exc
    return _require_dict(raw, context=str(path))


def load_coverage_report(path: Path) -> dict[str, object]:
    payload = _load_json(path)
    _require_string(payload, "brand", context=str(path))
    attempted = _require_int(payload, "products_attempted", context=str(path))
    succeeded = _require_int(payload, "products_succeeded", context=str(path))
    if attempted < 0 or succeeded < 0:
        raise CompletenessAnalyzerError(f"{path} product counters must be non-negative.")
    fields = _require_dict(payload.get("fields"), context=f"{path}.fields")
    for field_name in CRITICAL_FIELDS:
        field_payload = _require_dict(fields.get(field_name), context=f"{path}.fields.{field_name}")
        normalized_success = _require_int(
            field_payload,
            "normalized_success",
            context=f"{path}.fields.{field_name}",
        )
        if normalized_success < 0:
            raise CompletenessAnalyzerError(
                f"{path}.fields.{field_name}.normalized_success must be non-negative."
            )
    return payload


def analyze_brand(data_root: Path, *, brand: str, brand_type: str) -> BrandCompleteness:
    report_path = data_root / brand / "coverage_report.json"
    payload = load_coverage_report(report_path)
    attempted = _require_int(payload, "products_attempted", context=str(report_path))
    succeeded = _require_int(payload, "products_succeeded", context=str(report_path))
    denominator = succeeded if succeeded > 0 else attempted
    fields = _require_dict(payload["fields"], context=f"{report_path}.fields")

    critical_coverage: dict[str, float] = {}
    for field_name in CRITICAL_FIELDS:
        field_payload = _require_dict(fields[field_name], context=f"{report_path}.fields.{field_name}")
        normalized_success = _require_int(
            field_payload,
            "normalized_success",
            context=f"{report_path}.fields.{field_name}",
        )
        critical_coverage[field_name] = 0.0 if denominator <= 0 else normalized_success / denominator

    average = sum(critical_coverage.values()) / len(CRITICAL_FIELDS)
    return BrandCompleteness(
        brand=brand,
        brand_type=brand_type,
        models_attempted=attempted,
        models_succeeded=succeeded,
        critical_coverage=critical_coverage,
        average_critical_coverage=average,
    )


def analyze_brand_sets(data_root: Path, *, brand_set_names: tuple[str, ...]) -> list[BrandCompleteness]:
    results: list[BrandCompleteness] = []
    for brand_set_name in brand_set_names:
        try:
            brands = BRAND_SETS[brand_set_name]
        except KeyError as exc:
            raise CompletenessAnalyzerError(f"Unsupported brand set: {brand_set_name}") from exc
        for brand in brands:
            results.append(analyze_brand(data_root, brand=brand, brand_type=brand_set_name.capitalize()))
    return results


def format_text_report(results: list[BrandCompleteness]) -> str:
    lines = [
        "TECH SPEC COMPLETENESS ANALYSIS",
        f"Inputs: {SUPPORTED_INPUT_PATTERN}",
        "",
        "Brand            Type        Attempted  Succeeded  Motor   Battery  Weight  Speed   Avg",
        "-----------------------------------------------------------------------------------------",
    ]
    for result in results:
        motor = result.critical_coverage["motor_power_watts"] * 100
        battery = result.critical_coverage["battery_wh"] * 100
        weight = result.critical_coverage["weight_lbs"] * 100
        speed = result.critical_coverage["max_speed_mph"] * 100
        avg = result.average_critical_coverage * 100
        lines.append(
            f"{result.brand:<16} {result.brand_type:<11} {result.models_attempted:<10} "
            f"{result.models_succeeded:<10} {motor:>5.1f}%  {battery:>6.1f}%  {weight:>5.1f}%  "
            f"{speed:>5.1f}%  {avg:>5.1f}%"
        )
    return "\\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze spec completeness from explicit coverage reports only.")
    parser.add_argument("--data-root", type=Path, required=True, help="Path to the data directory.")
    parser.add_argument(
        "--brand-set",
        action="append",
        choices=tuple(BRAND_SETS),
        default=[],
        help="Brand set to analyze. Repeat to include multiple sets.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a text report.")
    parser.add_argument("--describe-schema", action="store_true", help="Print supported file/schema contract and exit.")
    args = parser.parse_args()

    if args.describe_schema:
        print(supported_schema_description())
        return 0

    brand_sets = tuple(args.brand_set) or ("affiliate", "official")
    try:
        results = analyze_brand_sets(args.data_root, brand_set_names=brand_sets)
    except CompletenessAnalyzerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "brand": result.brand,
                        "type": result.brand_type,
                        "models_attempted": result.models_attempted,
                        "models_succeeded": result.models_succeeded,
                        "critical_coverage": result.critical_coverage,
                        "average_critical_coverage": result.average_critical_coverage,
                    }
                    for result in results
                ],
                indent=2,
            )
        )
    else:
        print(format_text_report(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def build_image_analyzer_script() -> str:
    return """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze an image through Codex using an explicit file path.")
    parser.add_argument("--image-path", type=Path, required=True, help="Absolute path to the image file.")
    parser.add_argument("--prompt", required=True, help="Bounded analysis question for Codex.")
    args = parser.parse_args()

    image_path = args.image_path
    if not image_path.is_absolute():
        print("ERROR: --image-path must be an absolute file path.", file=sys.stderr)
        return 1
    if not image_path.exists():
        print(f"ERROR: image file does not exist: {image_path}", file=sys.stderr)
        return 1
    if shutil.which("codex") is None:
        print("ERROR: codex is not available on PATH.", file=sys.stderr)
        return 1

    result = subprocess.run(
        ["codex", "exec", "-i", str(image_path), args.prompt],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr or "ERROR: Codex image analysis failed.\\n")
        return result.returncode

    sys.stdout.write(result.stdout)
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
    (prompts_dir / "spec_completeness_analyzer.py").write_text(build_completeness_analyzer_script())
    (prompts_dir / "analyze_image.py").write_text(build_image_analyzer_script())


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


@app.command("analyze-completeness")
def analyze_completeness(
    data_root: Path = typer.Option(..., "--data-root", exists=True, file_okay=False, dir_okay=True),
    brand_set: list[str] | None = typer.Option(None, "--brand-set"),
    json_output: bool = typer.Option(False, "--json"),
    describe_schema: bool = typer.Option(False, "--describe-schema"),
) -> None:
    if describe_schema:
        typer.echo(supported_schema_description().rstrip())
        return

    brand_sets = tuple(brand_set) if brand_set else ("affiliate", "official")
    try:
        results = analyze_brand_sets(data_root, brand_set_names=brand_sets)
    except CompletenessAnalyzerError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(
            json.dumps(
                [
                    {
                        "brand": result.brand,
                        "type": result.brand_type,
                        "models_attempted": result.models_attempted,
                        "models_succeeded": result.models_succeeded,
                        "critical_coverage": result.critical_coverage,
                        "average_critical_coverage": result.average_critical_coverage,
                    }
                    for result in results
                ],
                indent=2,
            )
        )
        return

    typer.echo(format_text_report(results))


@app.command("analyze-image")
def analyze_image(
    image_path: Path = typer.Option(..., "--image-path", exists=True, dir_okay=False, readable=True),
    prompt: str = typer.Option(..., "--prompt"),
) -> None:
    if not image_path.is_absolute():
        typer.echo("ERROR: --image-path must be an absolute file path.", err=True)
        raise typer.Exit(code=1)
    if shutil.which("codex") is None:
        typer.echo("ERROR: codex is not available on PATH.", err=True)
        raise typer.Exit(code=1)
    result = subprocess.run(
        ["codex", "exec", "-i", str(image_path), prompt],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        typer.echo(result.stderr or "ERROR: Codex image analysis failed.", err=True)
        raise typer.Exit(code=result.returncode)
    typer.echo(result.stdout.rstrip())


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
