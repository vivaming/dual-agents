from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dual_agents.state import BoundedUnitState, RunState
from dual_agents.watchdog import WatchdogStatus, evaluate_watchdog
from dual_agents.workflow import WorkflowStage


def make_unit(**overrides: object) -> BoundedUnitState:
    base = {
        "unit_slug": "task-01-query-map",
        "stage": WorkflowStage.IMPLEMENTATION,
        "started_at": "2026-03-30T00:00:00Z",
        "updated_at": "2026-03-30T00:00:00Z",
        "last_progress_at": "2026-03-30T00:00:00Z",
        "last_heartbeat_at": None,
        "expected_lead_review_path": "/tmp/lead-review.txt",
        "expected_final_review_path": "/tmp/final-review.txt",
        "required_next_artifacts": ["builder_result"],
        "idle_timeout_seconds": 300,
        "hard_stop_timeout_seconds": 600,
    }
    base.update(overrides)
    return BoundedUnitState.model_validate(base)


def test_watchdog_warns_before_hard_stop() -> None:
    run_state = RunState(current_unit=make_unit())
    now = datetime(2026, 3, 30, 0, 5, 30, tzinfo=UTC)
    decision = evaluate_watchdog(run_state, now=now)
    assert decision.status == WatchdogStatus.WARN
    assert decision.idle_seconds == 330


def test_watchdog_stalls_after_hard_timeout() -> None:
    run_state = RunState(current_unit=make_unit())
    now = datetime(2026, 3, 30, 0, 11, 0, tzinfo=UTC)
    decision = evaluate_watchdog(run_state, now=now)
    assert decision.status == WatchdogStatus.STALLED
    assert "No artifact-backed progress" in decision.reason


def test_watchdog_stalls_missing_review_artifact() -> None:
    run_state = RunState(
        current_unit=make_unit(
            stage=WorkflowStage.CRITICAL_REVIEW,
            required_next_artifacts=["final_review_artifact"],
        )
    )
    now = datetime(2026, 3, 30, 0, 11, 0, tzinfo=UTC)
    decision = evaluate_watchdog(run_state, now=now)
    assert decision.status == WatchdogStatus.STALLED
    assert "Required review artifact missing" in decision.reason


def test_watchdog_escalates_repeated_idle_stall() -> None:
    run_state = RunState(current_unit=make_unit(inactivity_stall_count=1))
    now = datetime(2026, 3, 30, 0, 11, 0, tzinfo=UTC)
    decision = evaluate_watchdog(run_state, now=now)
    assert decision.status == WatchdogStatus.STALLED
    assert "Escalate the stalled unit" in decision.next_action
