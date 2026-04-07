import json
from pathlib import Path

from dual_agents.controller import (
    BoundedUnitStartMode,
    WorkflowController,
    WorkflowStage,
    analyze_initial_stage,
    choose_initial_stage,
)
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


def test_default_state_path_points_to_dual_agents_run_state(tmp_path: Path) -> None:
    assert default_state_path(tmp_path) == tmp_path / ".dual-agents" / "run-state.json"


def test_save_and_load_run_state_round_trip(tmp_path: Path) -> None:
    controller = WorkflowController(reviews_root=tmp_path / ".dual-agents" / "reviews")
    controller.begin_new_bounded_unit("task-01-query-map")
    run_state_path = default_state_path(tmp_path)
    save_run_state(run_state_path, RunState(current_unit=build_bounded_unit_state(controller)))
    loaded = load_run_state(run_state_path)
    assert loaded.current_unit is not None
    assert loaded.current_unit.unit_slug == "task-01-query-map"
    assert loaded.current_unit.stage == WorkflowStage.IMPLEMENTATION
    assert loaded.current_unit.required_next_artifacts == ["builder_result"]


def test_apply_run_state_restores_controller_fields(tmp_path: Path) -> None:
    state_path = default_state_path(tmp_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "current_unit": {
                    "unit_slug": "task-02-metadata",
                    "stage": "implementation",
                    "review_fix_rounds_used": 2,
                    "lead_review_required": False,
                    "critical_review_required": True,
                    "current_builder_task": "Fix metadata links.",
                    "current_builder_task_type": None,
                    "expected_lead_review_path": str(tmp_path / ".dual-agents" / "reviews" / "task-02-metadata" / "lead-review.txt"),
                    "expected_final_review_path": str(tmp_path / ".dual-agents" / "reviews" / "task-02-metadata" / "final-review.txt"),
                }
            }
        )
        + "\n"
    )
    controller = WorkflowController(reviews_root=tmp_path / ".dual-agents" / "reviews")
    apply_run_state(controller, load_run_state(state_path))
    assert controller.current_unit_slug == "task-02-metadata"
    assert controller.stage == WorkflowStage.IMPLEMENTATION
    assert controller.review_fix_rounds_used == 2
    assert controller.critical_review_required is True


def test_mark_heartbeat_updates_only_heartbeat_fields(tmp_path: Path) -> None:
    controller = WorkflowController(reviews_root=tmp_path / ".dual-agents" / "reviews")
    controller.begin_new_bounded_unit("task-03-watchdog")
    unit = build_bounded_unit_state(controller)
    updated = mark_heartbeat(unit, note="Waiting on bounded builder handoff result")
    assert updated.last_heartbeat_at is not None
    assert updated.last_progress_at == unit.last_progress_at
    assert updated.last_watchdog_warning == "Waiting on bounded builder handoff result"


def test_mark_stalled_sets_stage_and_reason(tmp_path: Path) -> None:
    controller = WorkflowController(reviews_root=tmp_path / ".dual-agents" / "reviews")
    controller.begin_new_bounded_unit("task-04-stop")
    unit = build_bounded_unit_state(controller)
    stalled = mark_stalled(unit, reason="Launcher schema missing subagent_type.")
    assert stalled.stage == WorkflowStage.STALLED
    assert stalled.last_stop_reason == "Launcher schema missing subagent_type."
    assert stalled.inactivity_stall_count == 1


def test_mark_progress_updates_blocking_issue_cluster(tmp_path: Path) -> None:
    controller = WorkflowController(reviews_root=tmp_path / ".dual-agents" / "reviews")
    controller.begin_new_bounded_unit("task-05-progress")
    unit = build_bounded_unit_state(controller)
    progressed = mark_progress(unit, stage=WorkflowStage.CRITICAL_REVIEW, open_blocking_issues=["fix malformed output"])
    assert progressed.stage == WorkflowStage.CRITICAL_REVIEW
    assert progressed.required_next_artifacts == ["final_review_artifact"]
    assert progressed.open_blocking_issues == ["fix malformed output"]


def test_choose_initial_stage_defaults_to_implementation() -> None:
    assert choose_initial_stage(start_mode=BoundedUnitStartMode.AUTO) == WorkflowStage.IMPLEMENTATION


def test_choose_initial_stage_detects_preimplementation_review() -> None:
    assert (
        choose_initial_stage(
            start_mode=BoundedUnitStartMode.AUTO,
            task_summary="Please do a lead review of this architecture plan before implementation starts.",
        )
        == WorkflowStage.EPIC_REVIEW
    )


def test_choose_initial_stage_uses_task_context() -> None:
    assert (
        choose_initial_stage(
            start_mode=BoundedUnitStartMode.AUTO,
            task_context="# Task\n\nThis is a pre-implementation design gate for the proposed architecture.",
        )
        == WorkflowStage.EPIC_REVIEW
    )


def test_analyze_initial_stage_prefers_implementation_for_delivery_shaped_epic() -> None:
    decision = analyze_initial_stage(
        start_mode=BoundedUnitStartMode.AUTO,
        task_context=(
            "# Task 03\n\n"
            "## Files\n- Modify: data/foo.json\n- Modify: scripts/build.py\n\n"
            "## Required Changes\nImplement the generator update.\n\n"
            "## Acceptance Criteria\nRendered output is updated.\n\n"
            "## Verification\npython3 scripts/build.py --dry-run\n"
        ),
    )
    assert decision.stage == WorkflowStage.IMPLEMENTATION
    assert decision.implementation_score >= decision.review_score


def test_analyze_initial_stage_prefers_review_for_design_session_statement() -> None:
    decision = analyze_initial_stage(
        start_mode=BoundedUnitStartMode.AUTO,
        task_summary="Use GPT to review the proposal and design the approach before implementation.",
    )
    assert decision.stage == WorkflowStage.EPIC_REVIEW
    assert decision.review_score > decision.implementation_score
