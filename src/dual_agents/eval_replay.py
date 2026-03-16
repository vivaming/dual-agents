from __future__ import annotations

import json
from dataclasses import dataclass

from dual_agents.cli import default_workflow_config
from dual_agents.controller import (
    TaskType,
    WorkflowController,
    WorkflowViolation,
    should_enter_forum_adjudication,
    validate_forum_ruling,
    validate_post_review_adjudication,
    validate_user_facing_report,
)
from dual_agents.workflow import WorkflowStage


@dataclass(frozen=True)
class ReplayScenario:
    name: str
    category: str
    critical: bool
    expected_forum: bool = False


SCENARIOS: tuple[ReplayScenario, ...] = (
    ReplayScenario("leaked_completeness_summary", "output_hygiene", True),
    ReplayScenario("post_review_broad_rewrite", "bounded_remediation", True),
    ReplayScenario("mixed_builder_handoff", "task_bounding", True),
    ReplayScenario("repeated_contradiction", "forum_applicability", True, expected_forum=True),
    ReplayScenario("clean_single_review", "forum_applicability", False, expected_forum=False),
    ReplayScenario("delivery_without_proof", "delivery_proof", True),
    ReplayScenario("forum_ruling_malformed", "forum_contract", False, expected_forum=True),
)


def _scenario_passes(config_forum_enabled: bool, scenario: ReplayScenario) -> bool:
    if scenario.name == "leaked_completeness_summary":
        try:
            validate_user_facing_report("Thinking: let me analyze the brands first")
        except WorkflowViolation:
            return True
        return False

    if scenario.name == "post_review_broad_rewrite":
        try:
            validate_post_review_adjudication(
                "Current unit status: CHANGES_REQUIRED\n"
                "Blocking issues:\n"
                "- issue 1\n"
                "- issue 2\n"
                "- issue 3\n"
                "- issue 4\n"
                "Next remediation unit: rewrite the whole design doc"
            )
        except WorkflowViolation:
            return True
        return False

    if scenario.name == "mixed_builder_handoff":
        controller = WorkflowController()
        controller.stage = WorkflowStage.IMPLEMENTATION
        try:
            controller.start_builder_handoff(
                "Build HTML and publish to prod",
                task_types=(TaskType.BUILD_RENDER, TaskType.PUBLISH),
            )
        except WorkflowViolation:
            return True
        return False

    if scenario.name == "repeated_contradiction":
        result = should_enter_forum_adjudication(
            repeated_review_cycles=2,
            conflicting_evidence=True,
            blocker_ambiguity=False,
            forum_enabled=config_forum_enabled,
        )
        return result is scenario.expected_forum

    if scenario.name == "clean_single_review":
        result = should_enter_forum_adjudication(
            repeated_review_cycles=0,
            conflicting_evidence=False,
            blocker_ambiguity=False,
            forum_enabled=config_forum_enabled,
        )
        return result is scenario.expected_forum

    if scenario.name == "delivery_without_proof":
        controller = WorkflowController(delivery_sensitive=True)
        controller.stage = WorkflowStage.ADJUDICATION
        controller.advance()
        try:
            controller.verify_delivery(artifact_proven=False, evidence_consistent=True)
        except WorkflowViolation:
            return True
        return False

    if scenario.name == "forum_ruling_malformed":
        if not config_forum_enabled:
            return False
        try:
            validate_forum_ruling(
                "Current dispute: x\nPerspectives:\n- one\n- two\n- three\n- four\nModerator ruling: y\nNext bounded action: z"
            )
        except WorkflowViolation:
            return True
        return False

    raise ValueError(f"Unknown scenario: {scenario.name}")


def evaluate_replay_scenarios() -> dict[str, object]:
    base_config = default_workflow_config().model_copy(update={"forum_adjudication_enabled": False})
    experiment_config = default_workflow_config().model_copy(update={"forum_adjudication_enabled": True})

    baseline_results = {scenario.name: _scenario_passes(base_config.forum_adjudication_enabled, scenario) for scenario in SCENARIOS}
    experiment_results = {
        scenario.name: _scenario_passes(experiment_config.forum_adjudication_enabled, scenario) for scenario in SCENARIOS
    }

    total = len(SCENARIOS)
    critical_total = sum(1 for s in SCENARIOS if s.critical)
    bounded_total = sum(1 for s in SCENARIOS if s.category in {"bounded_remediation", "task_bounding"})
    forum_total = sum(1 for s in SCENARIOS if s.category in {"forum_applicability", "forum_contract"})

    baseline_protected = sum(1 for v in baseline_results.values() if v)
    experiment_protected = sum(1 for v in experiment_results.values() if v)
    baseline_critical = sum(1 for s in SCENARIOS if s.critical and baseline_results[s.name])
    experiment_critical = sum(1 for s in SCENARIOS if s.critical and experiment_results[s.name])
    baseline_bounded = sum(
        1 for s in SCENARIOS if s.category in {"bounded_remediation", "task_bounding"} and baseline_results[s.name]
    )
    experiment_bounded = sum(
        1 for s in SCENARIOS if s.category in {"bounded_remediation", "task_bounding"} and experiment_results[s.name]
    )
    baseline_forum = sum(1 for s in SCENARIOS if s.category in {"forum_applicability", "forum_contract"} and baseline_results[s.name])
    experiment_forum = sum(
        1 for s in SCENARIOS if s.category in {"forum_applicability", "forum_contract"} and experiment_results[s.name]
    )

    return {
        "scenarios": [scenario.__dict__ for scenario in SCENARIOS],
        "baseline": {
            "scenario_protection_rate": round(baseline_protected / total, 3),
            "critical_failure_catch_rate": round(baseline_critical / critical_total, 3),
            "bounded_remediation_enforcement_rate": round(baseline_bounded / bounded_total, 3),
            "adjudication_applicability_rate": round(baseline_forum / forum_total, 3),
            "results": baseline_results,
        },
        "experiment": {
            "scenario_protection_rate": round(experiment_protected / total, 3),
            "critical_failure_catch_rate": round(experiment_critical / critical_total, 3),
            "bounded_remediation_enforcement_rate": round(experiment_bounded / bounded_total, 3),
            "adjudication_applicability_rate": round(experiment_forum / forum_total, 3),
            "results": experiment_results,
        },
        "delta": {
            "scenario_protection_gain": round((experiment_protected - baseline_protected) / total, 3),
            "critical_failure_catch_gain": round((experiment_critical - baseline_critical) / critical_total, 3),
            "bounded_remediation_gain": round((experiment_bounded - baseline_bounded) / bounded_total, 3),
            "adjudication_applicability_gain": round((experiment_forum - baseline_forum) / forum_total, 3),
        },
    }


def main() -> None:
    print(json.dumps(evaluate_replay_scenarios(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
