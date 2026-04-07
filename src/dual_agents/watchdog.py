from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from dual_agents.state import BoundedUnitState, RunState, parse_timestamp
from dual_agents.workflow import WorkflowStage


class WatchdogStatus(str, Enum):
    OK = "ok"
    WARN = "warn"
    STALLED = "stalled"


@dataclass(frozen=True)
class WatchdogDecision:
    status: WatchdogStatus
    reason: str
    idle_seconds: int
    expected_artifacts_missing: tuple[str, ...]
    next_action: str


def _artifact_paths(unit: BoundedUnitState) -> tuple[Path, ...]:
    paths: list[Path] = []
    if "lead_review_artifact" in unit.required_next_artifacts:
        paths.append(Path(unit.expected_lead_review_path))
    if "final_review_artifact" in unit.required_next_artifacts:
        paths.append(Path(unit.expected_final_review_path))
    return tuple(paths)


def _latest_progress_time(unit: BoundedUnitState) -> datetime:
    latest = parse_timestamp(unit.last_progress_at)
    for artifact_path in _artifact_paths(unit):
        if artifact_path.exists():
            artifact_time = datetime.fromtimestamp(artifact_path.stat().st_mtime, tz=UTC)
            if artifact_time > latest:
                latest = artifact_time
    return latest


def evaluate_watchdog(run_state: RunState, *, now: datetime | None = None) -> WatchdogDecision:
    if run_state.current_unit is None:
        return WatchdogDecision(
            status=WatchdogStatus.OK,
            reason="No active bounded unit in run-state.",
            idle_seconds=0,
            expected_artifacts_missing=(),
            next_action="Start a bounded unit before running the watchdog.",
        )

    unit = run_state.current_unit
    if unit.stage in {WorkflowStage.DEPLOY_READY, WorkflowStage.STALLED}:
        return WatchdogDecision(
            status=WatchdogStatus.OK,
            reason=f"Current unit is already {unit.stage.value}.",
            idle_seconds=0,
            expected_artifacts_missing=(),
            next_action="No watchdog action required.",
        )

    observed_now = now or datetime.now(UTC)
    latest_progress = _latest_progress_time(unit)
    idle_seconds = max(0, int((observed_now - latest_progress).total_seconds()))
    missing_artifacts = tuple(str(path) for path in _artifact_paths(unit) if not path.exists())

    if idle_seconds >= unit.hard_stop_timeout_seconds:
        reason = f"No artifact-backed progress for {idle_seconds}s."
        if missing_artifacts and unit.stage in {WorkflowStage.EPIC_REVIEW, WorkflowStage.CRITICAL_REVIEW}:
            reason = (
                f"Required review artifact missing after {idle_seconds}s: "
                + ", ".join(missing_artifacts)
            )
        next_action = "Record the unit as stalled and rerun the same bounded step with a clean handoff."
        if unit.inactivity_stall_count >= 1:
            next_action = "Escalate the stalled unit via forum adjudication, independent audit, or user-guided pause."
        return WatchdogDecision(
            status=WatchdogStatus.STALLED,
            reason=reason,
            idle_seconds=idle_seconds,
            expected_artifacts_missing=missing_artifacts,
            next_action=next_action,
        )

    if idle_seconds >= unit.idle_timeout_seconds:
        return WatchdogDecision(
            status=WatchdogStatus.WARN,
            reason=f"No artifact-backed progress for {idle_seconds}s.",
            idle_seconds=idle_seconds,
            expected_artifacts_missing=missing_artifacts,
            next_action="Record a heartbeat only if work is still active; otherwise stop and restart the bounded unit.",
        )

    return WatchdogDecision(
        status=WatchdogStatus.OK,
        reason="Recent progress is within the configured timeout window.",
        idle_seconds=idle_seconds,
        expected_artifacts_missing=missing_artifacts,
        next_action="No watchdog action required.",
    )
