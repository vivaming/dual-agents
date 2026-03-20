from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from dual_agents.stop_monitor import StopCategory
from dual_agents.workflow import WorkflowStage


class WorkflowViolation(ValueError):
    """Raised when the workflow attempts an invalid transition or accepts invalid evidence."""


class ReviewVerdict(str, Enum):
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"


class DeliveryProofStatus(str, Enum):
    PROVEN = "PROVEN"
    NOT_PROVEN = "NOT_PROVEN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class DecisionCategory(str, Enum):
    ORDINARY_IMPLEMENTATION = "ORDINARY_IMPLEMENTATION"
    NEW_TASKS = "NEW_TASKS"
    TASK_SEQUENCE_CHANGE = "TASK_SEQUENCE_CHANGE"
    EXCEPTION_CLASSIFICATION = "EXCEPTION_CLASSIFICATION"
    BLOCKER_CLASSIFICATION = "BLOCKER_CLASSIFICATION"
    AMBIGUOUS_PROGRESSION = "AMBIGUOUS_PROGRESSION"
    LATE_UNIT_SKIP = "LATE_UNIT_SKIP"


class TaskType(str, Enum):
    CONTENT_EDIT = "CONTENT_EDIT"
    BUILD_RENDER = "BUILD_RENDER"
    DATA_FIX = "DATA_FIX"
    SCRIPT_FIX = "SCRIPT_FIX"
    PUBLISH = "PUBLISH"
    DEPLOY = "DEPLOY"
    EXTERNAL_RECONFIG = "EXTERNAL_RECONFIG"


class HighRiskAction(str, Enum):
    PRODUCTION_PUBLISH = "PRODUCTION_PUBLISH"
    DEPLOYMENT_CHANGE = "DEPLOYMENT_CHANGE"
    EXTERNAL_SYSTEM_RECONFIG = "EXTERNAL_SYSTEM_RECONFIG"


class BuilderVerdict(str, Enum):
    PASS = "PASS"
    CHANGES_REQUIRED = "CHANGES_REQUIRED"
    BLOCKED = "BLOCKED"
    STALLED = "STALLED"


@dataclass(frozen=True)
class ReviewResult:
    verdict: ReviewVerdict
    blocking_issues: tuple[str, ...]
    non_blocking_issues: tuple[str, ...]
    delivery_proof_status: DeliveryProofStatus
    suggested_next_action: str

    @property
    def has_blocking_issues(self) -> bool:
        return self.verdict == ReviewVerdict.CHANGES_REQUESTED or bool(self.blocking_issues)


@dataclass(frozen=True)
class BuilderResult:
    verdict: BuilderVerdict
    files_changed: tuple[str, ...]
    tests_run: tuple[str, ...]
    blockers: tuple[str, ...]
    next_action: str

    @property
    def requires_follow_up(self) -> bool:
        return self.verdict in {BuilderVerdict.CHANGES_REQUIRED, BuilderVerdict.BLOCKED, BuilderVerdict.STALLED}


FIELD_PATTERNS = {
    "verdict": re.compile(r"^\s*(?:\d+\.\s*)?Verdict:\s*(.+?)\s*$", re.IGNORECASE),
    "blocking_issues": re.compile(r"^\s*(?:\d+\.\s*)?Blocking issues:\s*(.*?)\s*$", re.IGNORECASE),
    "non_blocking_issues": re.compile(r"^\s*(?:\d+\.\s*)?Non-blocking issues:\s*(.*?)\s*$", re.IGNORECASE),
    "delivery_proof_status": re.compile(
        r"^\s*(?:\d+\.\s*)?Delivery proof status:\s*(.+?)\s*$", re.IGNORECASE
    ),
    "suggested_next_action": re.compile(
        r"^\s*(?:\d+\.\s*)?Suggested next action:\s*(.+?)\s*$", re.IGNORECASE
    ),
}

BUILDER_FIELD_PATTERNS = {
    "verdict": re.compile(r"^\s*(?:\d+\.\s*)?Status:\s*(.+?)\s*$", re.IGNORECASE),
    "files_changed": re.compile(r"^\s*(?:\d+\.\s*)?Files changed:\s*(.*?)\s*$", re.IGNORECASE),
    "tests_run": re.compile(r"^\s*(?:\d+\.\s*)?Tests run:\s*(.*?)\s*$", re.IGNORECASE),
    "blockers": re.compile(r"^\s*(?:\d+\.\s*)?Blockers:\s*(.*?)\s*$", re.IGNORECASE),
    "next_action": re.compile(r"^\s*(?:\d+\.\s*)?Next action:\s*(.+?)\s*$", re.IGNORECASE),
}

INTERNAL_LEAK_PATTERNS = (
    re.compile(r"^\s*Thinking:\s*", re.IGNORECASE | re.MULTILINE),
    re.compile(r"<(?:system|parameter|invoke)\b", re.IGNORECASE),
    re.compile(r"^\s*#\s+Analyze\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*\$\s+python", re.IGNORECASE | re.MULTILINE),
)

ANALYSIS_FAILURE_PATTERNS = (
    re.compile(r"Traceback \(most recent call last\):", re.IGNORECASE),
    re.compile(r"\bAttributeError:", re.IGNORECASE),
    re.compile(r"\bSyntaxError:", re.IGNORECASE),
    re.compile(r"\bTypeError:", re.IGNORECASE),
    re.compile(r"\bKeyError:", re.IGNORECASE),
    re.compile(r"\bJSONDecodeError:", re.IGNORECASE),
)

ANALYSIS_RECOVERY_STEPS = (
    "inspect schema",
    "fix parser",
    "rerun same bounded analysis",
)

UNSAFE_STAGE_PATTERNS = (
    re.compile(r"\bgit\s+add\s+-A\b", re.IGNORECASE),
    re.compile(r"\bgit\s+add\s+--all\b", re.IGNORECASE),
    re.compile(r"\bgit\s+add\s+\.\b", re.IGNORECASE),
    re.compile(r"\bgit\s+add\b.*[*?\[]", re.IGNORECASE),
)


def _normalize_issues(raw_value: str, continuation_lines: list[str]) -> tuple[str, ...]:
    candidates: list[str] = []
    if raw_value and raw_value.lower() not in {"none", "n/a"}:
        candidates.append(raw_value)
    for line in continuation_lines:
        item = re.sub(r"^\s*[-*]\s*", "", line).strip()
        if item:
            candidates.append(item)
    return tuple(candidates)


def parse_review_result(raw_review: str) -> ReviewResult:
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

    required_fields = {"verdict", "blocking_issues", "non_blocking_issues", "delivery_proof_status", "suggested_next_action"}
    missing_fields = sorted(required_fields - captured.keys())
    if missing_fields:
        raise WorkflowViolation(f"Review output missing required fields: {', '.join(missing_fields)}")

    try:
        verdict = ReviewVerdict(captured["verdict"].upper())
    except ValueError as exc:
        raise WorkflowViolation(f"Invalid review verdict: {captured['verdict']}") from exc

    try:
        delivery_proof_status = DeliveryProofStatus(captured["delivery_proof_status"].upper())
    except ValueError as exc:
        raise WorkflowViolation(
            f"Invalid delivery proof status: {captured['delivery_proof_status']}"
        ) from exc

    suggested_next_action = captured["suggested_next_action"].strip()
    if not suggested_next_action:
        raise WorkflowViolation("Suggested next action must not be empty.")

    return ReviewResult(
        verdict=verdict,
        blocking_issues=_normalize_issues(captured["blocking_issues"], continuations["blocking_issues"]),
        non_blocking_issues=_normalize_issues(
            captured["non_blocking_issues"], continuations["non_blocking_issues"]
        ),
        delivery_proof_status=delivery_proof_status,
        suggested_next_action=suggested_next_action,
    )


def parse_builder_result(raw_result: str) -> BuilderResult:
    captured: dict[str, str] = {}
    continuations: dict[str, list[str]] = {
        "files_changed": [],
        "tests_run": [],
        "blockers": [],
    }
    active_multiline_field: str | None = None

    for line in raw_result.splitlines():
        matched_field = None
        for field_name, pattern in BUILDER_FIELD_PATTERNS.items():
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

    required_fields = {"verdict", "files_changed", "tests_run", "blockers", "next_action"}
    missing_fields = sorted(required_fields - captured.keys())
    if missing_fields:
        raise WorkflowViolation(f"Builder output missing required fields: {', '.join(missing_fields)}")

    try:
        verdict = BuilderVerdict(captured["verdict"].upper())
    except ValueError as exc:
        raise WorkflowViolation(f"Invalid builder status: {captured['verdict']}") from exc

    next_action = captured["next_action"].strip()
    if not next_action:
        raise WorkflowViolation("Builder next action must not be empty.")

    return BuilderResult(
        verdict=verdict,
        files_changed=_normalize_issues(captured["files_changed"], continuations["files_changed"]),
        tests_run=_normalize_issues(captured["tests_run"], continuations["tests_run"]),
        blockers=_normalize_issues(captured["blockers"], continuations["blockers"]),
        next_action=next_action,
    )


def contains_internal_leak(raw_output: str) -> bool:
    return any(pattern.search(raw_output) for pattern in INTERNAL_LEAK_PATTERNS)


def contains_analysis_traceback(raw_output: str) -> bool:
    return any(pattern.search(raw_output) for pattern in ANALYSIS_FAILURE_PATTERNS)


def build_analysis_failure_stop_report(raw_output: str, *, unit_name: str) -> str:
    if not contains_analysis_traceback(raw_output):
        raise WorkflowViolation("Analysis stop report requires traceback-style evidence.")
    evidence: list[str] = []
    for line in raw_output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(pattern.search(stripped) for pattern in ANALYSIS_FAILURE_PATTERNS):
            evidence.append(stripped)
    evidence_lines = "\n".join(f"- {item}" for item in tuple(dict.fromkeys(evidence))[:4]) or "- none captured"
    recovery = "Inspect schema, fix parser, and rerun the same bounded analysis."
    return (
        f"Current unit: {unit_name}\n"
        f"Stop signal: {StopCategory.DATA_SHAPE_MISMATCH.value}\n"
        f"Matched categories: {StopCategory.DATA_SHAPE_MISMATCH.value}\n"
        "Evidence:\n"
        f"{evidence_lines}\n"
        f"Next recovery step: {recovery}"
    )


def validate_analysis_recovery_step(step: str) -> str:
    cleaned = step.strip().lower()
    if cleaned not in ANALYSIS_RECOVERY_STEPS:
        raise WorkflowViolation(
            "Analysis recovery must be one of: "
            + ", ".join(ANALYSIS_RECOVERY_STEPS)
        )
    return cleaned


def validate_user_facing_report(raw_output: str, *, required_terms: tuple[str, ...] = ()) -> str:
    cleaned = raw_output.strip()
    if not cleaned:
        raise WorkflowViolation("User-facing report must not be empty.")
    if contains_internal_leak(cleaned):
        raise WorkflowViolation(
            "User-facing report leaked internal reasoning, tool syntax, or control tags."
        )
    missing_terms = [term for term in required_terms if term not in cleaned]
    if missing_terms:
        raise WorkflowViolation(
            f"User-facing report omitted required requested content: {', '.join(missing_terms)}"
        )
    return cleaned


def build_remediation_issue_cluster(issues: tuple[str, ...], *, max_items: int = 3) -> tuple[str, ...]:
    if max_items < 1:
        raise WorkflowViolation("Issue cluster limit must be at least 1.")
    cleaned = tuple(issue.strip() for issue in issues if issue.strip())
    if not cleaned:
        raise WorkflowViolation("Cannot build a remediation cluster from an empty issue list.")
    return cleaned[:max_items]


def contains_unsafe_stage_command(raw_command: str) -> bool:
    return any(pattern.search(raw_command) for pattern in UNSAFE_STAGE_PATTERNS)


def validate_staging_scope(
    *,
    repo_dirty_file_count: int,
    requested_file_count: int,
    contains_directory_path: bool = False,
    has_unrelated_dirty_files: bool = False,
    max_files: int = 25,
) -> None:
    if requested_file_count < 1:
        raise WorkflowViolation("Staging plan must name at least one explicit file.")
    if contains_directory_path:
        raise WorkflowViolation("Directory-wide staging is not allowed for a dirty repo; use explicit files.")
    if repo_dirty_file_count > 0 and has_unrelated_dirty_files:
        raise WorkflowViolation("Dirty repo contains unrelated changes; isolate the unit in a worktree before staging.")
    if requested_file_count > max_files:
        raise WorkflowViolation(f"Staging plan touches {requested_file_count} files; limit is {max_files}.")


def validate_post_review_adjudication(raw_output: str, *, max_issue_count: int = 3) -> str:
    cleaned = validate_user_facing_report(raw_output)
    required_labels = (
        "Current unit status:",
        "Blocking issues:",
        "Next remediation unit:",
    )
    missing_labels = [label for label in required_labels if label not in cleaned]
    if missing_labels:
        raise WorkflowViolation(
            "Post-review adjudication missing required labels: " + ", ".join(missing_labels)
        )
    issue_lines = [
        line for line in cleaned.splitlines()
        if line.strip().startswith("- ") and "Blocking issues:" not in line
    ]
    if len(issue_lines) > max_issue_count:
        raise WorkflowViolation(
            f"Post-review adjudication listed {len(issue_lines)} issues; limit is {max_issue_count}."
        )
    if len(cleaned) > 1800:
        raise WorkflowViolation("Post-review adjudication is too long; keep it concise and bounded.")
    return cleaned


def should_enter_forum_adjudication(
    *,
    repeated_review_cycles: int,
    conflicting_evidence: bool,
    blocker_ambiguity: bool,
    forum_enabled: bool,
) -> bool:
    if not forum_enabled:
        return False
    return repeated_review_cycles >= 2 or conflicting_evidence or blocker_ambiguity


def validate_forum_ruling(raw_output: str, *, max_perspectives: int = 3) -> str:
    cleaned = validate_user_facing_report(raw_output)
    required_labels = (
        "Current dispute:",
        "Perspectives:",
        "Moderator ruling:",
        "Next bounded action:",
    )
    missing_labels = [label for label in required_labels if label not in cleaned]
    if missing_labels:
        raise WorkflowViolation("Forum ruling missing required labels: " + ", ".join(missing_labels))
    perspective_lines = [
        line for line in cleaned.splitlines()
        if line.strip().startswith("- ") and "Perspectives:" not in line
    ]
    if len(perspective_lines) > max_perspectives:
        raise WorkflowViolation(
            f"Forum ruling listed {len(perspective_lines)} perspectives; limit is {max_perspectives}."
        )
    if len(cleaned) > 1600:
        raise WorkflowViolation("Forum ruling is too long; keep it concise and bounded.")
    return cleaned


def requires_critical_review(
    *,
    decision_category: DecisionCategory,
    current_unit_status: str | None = None,
) -> bool:
    if decision_category in {
        DecisionCategory.NEW_TASKS,
        DecisionCategory.TASK_SEQUENCE_CHANGE,
        DecisionCategory.EXCEPTION_CLASSIFICATION,
        DecisionCategory.BLOCKER_CLASSIFICATION,
        DecisionCategory.AMBIGUOUS_PROGRESSION,
        DecisionCategory.LATE_UNIT_SKIP,
    }:
        return True

    if current_unit_status and current_unit_status.upper() in {"PARTIAL", "UNCLEAR", "MIXED"}:
        return True

    return False


def requires_premium_review(
    *,
    premium_optimize_enabled: bool,
    decision_category: DecisionCategory = DecisionCategory.ORDINARY_IMPLEMENTATION,
    delivery_sensitive: bool = False,
    conflicting_evidence: bool = False,
    repeated_review_cycles: int = 0,
    high_risk_actions: tuple[HighRiskAction, ...] = (),
    current_unit_status: str | None = None,
    premium_on_new_tasks: bool = True,
    premium_on_task_sequence_change: bool = True,
    premium_on_high_risk_actions: bool = True,
    premium_on_conflicting_evidence: bool = True,
    premium_on_repeated_review_cycles: int = 2,
    premium_on_delivery_sensitive: bool = True,
) -> bool:
    if not premium_optimize_enabled:
        return True

    if current_unit_status and current_unit_status.upper() in {"PARTIAL", "UNCLEAR", "MIXED"}:
        return True

    if premium_on_new_tasks and decision_category == DecisionCategory.NEW_TASKS:
        return True
    if premium_on_task_sequence_change and decision_category == DecisionCategory.TASK_SEQUENCE_CHANGE:
        return True
    if premium_on_high_risk_actions and high_risk_actions:
        return True
    if premium_on_conflicting_evidence and conflicting_evidence:
        return True
    if repeated_review_cycles >= premium_on_repeated_review_cycles:
        return True
    if premium_on_delivery_sensitive and delivery_sensitive:
        return True
    return False


def is_bounded_builder_task(task_summary: str) -> bool:
    lowered = task_summary.lower()
    broad_markers = (" and ", " then ", ";", " after that ", " once it is done ")
    if any(marker in lowered for marker in broad_markers):
        return False
    return True


@dataclass
class WorkflowController:
    delivery_sensitive: bool = False
    stage: WorkflowStage = WorkflowStage.REQUEST_RECEIVED
    last_review_result: ReviewResult | None = field(default=None, init=False)
    last_builder_result: BuilderResult | None = field(default=None, init=False)
    critical_review_required: bool = field(default=False, init=False)
    builder_handoff_active: bool = field(default=False, init=False)
    current_builder_task: str | None = field(default=None, init=False)
    current_builder_task_type: TaskType | None = field(default=None, init=False)
    forum_rounds_used: int = field(default=0, init=False)
    analysis_hard_stop_active: bool = field(default=False, init=False)

    def flag_decision_for_review(
        self,
        *,
        decision_category: DecisionCategory,
        current_unit_status: str | None = None,
    ) -> bool:
        self.critical_review_required = requires_critical_review(
            decision_category=decision_category,
            current_unit_status=current_unit_status,
        )
        return self.critical_review_required

    def advance(self) -> WorkflowStage:
        if self.analysis_hard_stop_active:
            raise WorkflowViolation(
                "Analysis hard-stop is active; recover with inspect schema, fix parser, then rerun the same bounded analysis."
            )
        if self.stage == WorkflowStage.REQUEST_RECEIVED:
            self.stage = WorkflowStage.EPIC_DRAFT
        elif self.stage == WorkflowStage.EPIC_DRAFT:
            self.stage = WorkflowStage.EPIC_REVIEW
        elif self.stage == WorkflowStage.EPIC_REVIEW:
            if self.critical_review_required:
                raise WorkflowViolation(
                    "Critical review is required before advancing from EPIC_REVIEW to implementation."
                )
            self.stage = WorkflowStage.IMPLEMENTATION
        elif self.stage == WorkflowStage.IMPLEMENTATION:
            if self.builder_handoff_active:
                raise WorkflowViolation("Builder handoff is still active; wait for a structured result or mark it stalled.")
            self.stage = WorkflowStage.SELF_REVIEW
        elif self.stage == WorkflowStage.SELF_REVIEW:
            self.stage = WorkflowStage.CRITICAL_REVIEW
        elif self.stage == WorkflowStage.ADJUDICATION:
            if self.critical_review_required and self.last_review_result is None:
                raise WorkflowViolation("Critical review is required before adjudication may advance.")
            self.stage = (
                WorkflowStage.DELIVERY_VERIFICATION if self.delivery_sensitive else WorkflowStage.DEPLOY_READY
            )
        elif self.stage == WorkflowStage.FORUM_ADJUDICATION:
            self.stage = WorkflowStage.IMPLEMENTATION
        elif self.stage == WorkflowStage.DELIVERY_VERIFICATION:
            raise WorkflowViolation("Delivery verification requires explicit proof; use verify_delivery().")
        elif self.stage == WorkflowStage.DEPLOY_READY:
            self.stage = WorkflowStage.DEPLOY_READY
        else:
            raise WorkflowViolation(f"Cannot advance automatically from stage {self.stage}.")
        return self.stage

    def submit_review(self, raw_review: str) -> ReviewResult:
        if self.stage != WorkflowStage.CRITICAL_REVIEW:
            raise WorkflowViolation("Review results may only be submitted during CRITICAL_REVIEW.")
        review_result = parse_review_result(raw_review)
        self.last_review_result = review_result
        self.critical_review_required = False
        self.stage = WorkflowStage.IMPLEMENTATION if review_result.has_blocking_issues else WorkflowStage.ADJUDICATION
        return review_result

    def start_builder_handoff(
        self,
        task_summary: str,
        *,
        task_types: tuple[TaskType, ...] = (),
        high_risk_actions: tuple[HighRiskAction, ...] = (),
        explicitly_reviewed: bool = False,
    ) -> str:
        if self.analysis_hard_stop_active:
            raise WorkflowViolation(
                "Analysis hard-stop is active; do not jump to another task before schema inspection, parser fix, and rerun."
            )
        if self.stage != WorkflowStage.IMPLEMENTATION:
            raise WorkflowViolation("Builder handoff may only start during IMPLEMENTATION.")
        bounded_task = task_summary.strip()
        if not bounded_task:
            raise WorkflowViolation("Builder handoff requires a non-empty bounded task.")
        if not is_bounded_builder_task(bounded_task):
            raise WorkflowViolation("Builder handoff must contain one bounded task, not a chained multi-step request.")
        if len(task_types) != 1:
            raise WorkflowViolation("Builder handoff must declare exactly one task type.")
        if high_risk_actions and not explicitly_reviewed:
            raise WorkflowViolation("High-risk actions require an explicit review gate before builder execution.")
        self.builder_handoff_active = True
        self.current_builder_task = bounded_task
        self.current_builder_task_type = task_types[0]
        return bounded_task

    def submit_builder_result(self, raw_result: str) -> BuilderResult:
        if self.stage != WorkflowStage.IMPLEMENTATION or not self.builder_handoff_active:
            raise WorkflowViolation("No active builder handoff is awaiting a result.")
        if not raw_result.strip():
            return self._stall_builder("Builder returned empty output.")
        builder_result = parse_builder_result(raw_result)
        self.last_builder_result = builder_result
        self.builder_handoff_active = False
        self.current_builder_task = None
        self.current_builder_task_type = None
        if builder_result.verdict == BuilderVerdict.STALLED:
            self.stage = WorkflowStage.IMPLEMENTATION
            raise WorkflowViolation("Builder reported STALLED; coordinator must split scope or pause.")
        return builder_result

    def mark_builder_stalled(self, reason: str) -> WorkflowStage:
        if self.stage != WorkflowStage.IMPLEMENTATION or not self.builder_handoff_active:
            raise WorkflowViolation("Cannot mark builder stalled without an active builder handoff.")
        self._stall_builder(reason)
        raise WorkflowViolation("Builder handoff stalled; coordinator must recover before continuing.")

    def _stall_builder(self, reason: str) -> BuilderResult:
        self.last_builder_result = BuilderResult(
            verdict=BuilderVerdict.STALLED,
            files_changed=(),
            tests_run=(),
            blockers=(reason.strip() or "Builder handoff stalled.",),
            next_action="Split the task into a smaller bounded unit or pause for guidance.",
        )
        self.builder_handoff_active = False
        self.current_builder_task = None
        self.current_builder_task_type = None
        self.stage = WorkflowStage.IMPLEMENTATION
        return self.last_builder_result

    def verify_delivery(self, *, artifact_proven: bool, evidence_consistent: bool) -> WorkflowStage:
        if self.stage != WorkflowStage.DELIVERY_VERIFICATION:
            raise WorkflowViolation("Delivery may only be verified during DELIVERY_VERIFICATION.")
        if not self.delivery_sensitive:
            raise WorkflowViolation("Delivery verification is only valid for delivery-sensitive tasks.")
        if not evidence_consistent:
            raise WorkflowViolation("Conflicting evidence blocks workflow completion.")
        if not artifact_proven:
            raise WorkflowViolation("Remote artifact proof is required before completion.")
        self.stage = WorkflowStage.DEPLOY_READY
        return self.stage

    def enter_forum_adjudication(self, *, forum_max_rounds: int) -> WorkflowStage:
        if self.stage not in {WorkflowStage.ADJUDICATION, WorkflowStage.IMPLEMENTATION}:
            raise WorkflowViolation("Forum adjudication may only start from ADJUDICATION or IMPLEMENTATION.")
        if self.forum_rounds_used >= forum_max_rounds:
            raise WorkflowViolation("Forum adjudication round limit exceeded.")
        self.forum_rounds_used += 1
        self.stage = WorkflowStage.FORUM_ADJUDICATION
        return self.stage

    def hard_stop_analysis_failure(self, raw_output: str, *, unit_name: str) -> str:
        report = build_analysis_failure_stop_report(raw_output, unit_name=unit_name)
        self.analysis_hard_stop_active = True
        return report

    def clear_analysis_hard_stop(self, recovery_step: str) -> None:
        validate_analysis_recovery_step(recovery_step)
        self.analysis_hard_stop_active = False
