from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from dual_agents.controller import TaskType, WorkflowController
from dual_agents.workflow import WorkflowStage


def utc_now() -> datetime:
    return datetime.now(UTC)


def timestamp_now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized)


def stage_required_artifacts(stage: WorkflowStage) -> list[str]:
    if stage == WorkflowStage.EPIC_REVIEW:
        return ["lead_review_artifact"]
    if stage == WorkflowStage.CRITICAL_REVIEW:
        return ["final_review_artifact"]
    if stage == WorkflowStage.IMPLEMENTATION:
        return ["builder_result"]
    return []


def stage_timeouts(stage: WorkflowStage) -> tuple[int, int]:
    if stage in {WorkflowStage.EPIC_REVIEW, WorkflowStage.CRITICAL_REVIEW, WorkflowStage.FORUM_ADJUDICATION}:
        return (180, 420)
    return (300, 600)


class BoundedUnitState(BaseModel):
    unit_slug: str = Field(min_length=1)
    stage: WorkflowStage
    started_at: str = Field(default_factory=timestamp_now)
    updated_at: str = Field(default_factory=timestamp_now)
    last_progress_at: str = Field(default_factory=timestamp_now)
    last_heartbeat_at: str | None = None
    review_fix_rounds_used: int = 0
    lead_review_required: bool = False
    critical_review_required: bool = False
    current_builder_task: str | None = None
    current_builder_task_type: str | None = None
    expected_lead_review_path: str
    expected_final_review_path: str
    required_next_artifacts: list[str] = Field(default_factory=list)
    open_blocking_issues: list[str] = Field(default_factory=list)
    last_stop_reason: str | None = None
    last_watchdog_warning: str | None = None
    idle_timeout_seconds: int = 300
    hard_stop_timeout_seconds: int = 600
    inactivity_stall_count: int = 0


class RunState(BaseModel):
    current_unit: BoundedUnitState | None = None


def default_state_path(repo_root: Path) -> Path:
    return repo_root / ".dual-agents" / "run-state.json"


def load_run_state(state_path: Path) -> RunState:
    if not state_path.exists():
        return RunState()
    return RunState.model_validate_json(state_path.read_text())


def save_run_state(state_path: Path, run_state: RunState) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(run_state.model_dump(mode="json"), indent=2) + "\n")


def build_bounded_unit_state(controller: WorkflowController) -> BoundedUnitState:
    if not controller.current_unit_slug:
        raise ValueError("Controller has no current bounded unit slug.")

    lead_path = controller.reviews_root / controller.current_unit_slug / "lead-review.txt"
    final_path = controller.reviews_root / controller.current_unit_slug / "final-review.txt"
    idle_timeout_seconds, hard_stop_timeout_seconds = stage_timeouts(controller.stage)
    return BoundedUnitState(
        unit_slug=controller.current_unit_slug,
        stage=controller.stage,
        review_fix_rounds_used=controller.review_fix_rounds_used,
        lead_review_required=controller.lead_review_required,
        critical_review_required=controller.critical_review_required,
        current_builder_task=controller.current_builder_task,
        current_builder_task_type=controller.current_builder_task_type.value
        if controller.current_builder_task_type
        else None,
        expected_lead_review_path=str(lead_path),
        expected_final_review_path=str(final_path),
        required_next_artifacts=stage_required_artifacts(controller.stage),
        idle_timeout_seconds=idle_timeout_seconds,
        hard_stop_timeout_seconds=hard_stop_timeout_seconds,
    )


def apply_run_state(controller: WorkflowController, run_state: RunState) -> WorkflowController:
    if run_state.current_unit is None:
        return controller
    unit = run_state.current_unit
    controller.current_unit_slug = unit.unit_slug
    controller.stage = unit.stage
    controller.review_fix_rounds_used = unit.review_fix_rounds_used
    controller.lead_review_required = unit.lead_review_required
    controller.critical_review_required = unit.critical_review_required
    controller.current_builder_task = unit.current_builder_task
    controller.current_builder_task_type = TaskType(unit.current_builder_task_type) if unit.current_builder_task_type else None
    controller.builder_handoff_active = bool(unit.current_builder_task)
    return controller


def mark_progress(unit: BoundedUnitState, *, stage: WorkflowStage | None = None, open_blocking_issues: list[str] | None = None) -> BoundedUnitState:
    now = timestamp_now()
    next_stage = stage or unit.stage
    idle_timeout_seconds, hard_stop_timeout_seconds = stage_timeouts(next_stage)
    updated = unit.model_copy(
        update={
            "stage": next_stage,
            "updated_at": now,
            "last_progress_at": now,
            "required_next_artifacts": stage_required_artifacts(next_stage),
            "open_blocking_issues": open_blocking_issues if open_blocking_issues is not None else unit.open_blocking_issues,
            "last_watchdog_warning": None,
            "idle_timeout_seconds": idle_timeout_seconds,
            "hard_stop_timeout_seconds": hard_stop_timeout_seconds,
        }
    )
    return updated


def mark_heartbeat(unit: BoundedUnitState, *, note: str | None = None) -> BoundedUnitState:
    now = timestamp_now()
    warning = note.strip() if note else unit.last_watchdog_warning
    return unit.model_copy(
        update={
            "updated_at": now,
            "last_heartbeat_at": now,
            "last_watchdog_warning": warning,
        }
    )


def mark_stalled(unit: BoundedUnitState, *, reason: str) -> BoundedUnitState:
    now = timestamp_now()
    return unit.model_copy(
        update={
            "stage": WorkflowStage.STALLED,
            "updated_at": now,
            "last_stop_reason": reason.strip(),
            "last_watchdog_warning": None,
            "required_next_artifacts": [],
            "inactivity_stall_count": unit.inactivity_stall_count + 1,
        }
    )
