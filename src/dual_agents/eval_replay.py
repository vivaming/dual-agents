from __future__ import annotations

import json
from dataclasses import dataclass

from dual_agents.cli import default_workflow_config
from dual_agents.controller import (
    DecisionCategory,
    HighRiskAction,
    TaskType,
    WorkflowController,
    WorkflowViolation,
    requires_premium_review,
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
    review_packet_chars: int = 800
    decision_category: DecisionCategory = DecisionCategory.ORDINARY_IMPLEMENTATION
    delivery_sensitive: bool = False
    conflicting_evidence: bool = False
    repeated_review_cycles: int = 0
    high_risk_actions: tuple[HighRiskAction, ...] = ()


SCENARIOS: tuple[ReplayScenario, ...] = (
    ReplayScenario("leaked_completeness_summary", "output_hygiene", True, review_packet_chars=650),
    ReplayScenario("post_review_broad_rewrite", "bounded_remediation", True, review_packet_chars=1100),
    ReplayScenario("mixed_builder_handoff", "task_bounding", True, review_packet_chars=900),
    ReplayScenario(
        "repeated_contradiction",
        "forum_applicability",
        True,
        expected_forum=True,
        review_packet_chars=1400,
        conflicting_evidence=True,
        repeated_review_cycles=2,
    ),
    ReplayScenario("clean_single_review", "forum_applicability", False, expected_forum=False, review_packet_chars=700),
    ReplayScenario(
        "delivery_without_proof",
        "delivery_proof",
        True,
        review_packet_chars=950,
        delivery_sensitive=True,
        high_risk_actions=(HighRiskAction.PRODUCTION_PUBLISH,),
    ),
    ReplayScenario(
        "forum_ruling_malformed",
        "forum_contract",
        False,
        expected_forum=True,
        review_packet_chars=850,
        conflicting_evidence=True,
        repeated_review_cycles=2,
    ),
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
    experiment_config = default_workflow_config().model_copy(
        update={"forum_adjudication_enabled": True, "premium_review_optimize_enabled": True}
    )

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
    baseline_premium_calls = len(SCENARIOS)
    experiment_premium_calls = sum(
        1
        for s in SCENARIOS
        if requires_premium_review(
            premium_optimize_enabled=experiment_config.premium_review_optimize_enabled,
            decision_category=s.decision_category,
            delivery_sensitive=s.delivery_sensitive,
            conflicting_evidence=s.conflicting_evidence,
            repeated_review_cycles=s.repeated_review_cycles,
            high_risk_actions=s.high_risk_actions,
            premium_on_new_tasks=experiment_config.premium_review_on_new_tasks,
            premium_on_task_sequence_change=experiment_config.premium_review_on_task_sequence_change,
            premium_on_high_risk_actions=experiment_config.premium_review_on_high_risk_actions,
            premium_on_conflicting_evidence=experiment_config.premium_review_on_conflicting_evidence,
            premium_on_repeated_review_cycles=experiment_config.premium_review_on_repeated_review_cycles,
            premium_on_delivery_sensitive=experiment_config.premium_review_on_delivery_sensitive,
        )
    )
    baseline_premium_chars = sum(s.review_packet_chars for s in SCENARIOS)
    experiment_premium_chars = sum(
        s.review_packet_chars
        for s in SCENARIOS
        if requires_premium_review(
            premium_optimize_enabled=experiment_config.premium_review_optimize_enabled,
            decision_category=s.decision_category,
            delivery_sensitive=s.delivery_sensitive,
            conflicting_evidence=s.conflicting_evidence,
            repeated_review_cycles=s.repeated_review_cycles,
            high_risk_actions=s.high_risk_actions,
            premium_on_new_tasks=experiment_config.premium_review_on_new_tasks,
            premium_on_task_sequence_change=experiment_config.premium_review_on_task_sequence_change,
            premium_on_high_risk_actions=experiment_config.premium_review_on_high_risk_actions,
            premium_on_conflicting_evidence=experiment_config.premium_review_on_conflicting_evidence,
            premium_on_repeated_review_cycles=experiment_config.premium_review_on_repeated_review_cycles,
            premium_on_delivery_sensitive=experiment_config.premium_review_on_delivery_sensitive,
        )
    )

    return {
        "scenarios": [scenario.__dict__ for scenario in SCENARIOS],
        "baseline": {
            "scenario_protection_rate": round(baseline_protected / total, 3),
            "critical_failure_catch_rate": round(baseline_critical / critical_total, 3),
            "bounded_remediation_enforcement_rate": round(baseline_bounded / bounded_total, 3),
            "adjudication_applicability_rate": round(baseline_forum / forum_total, 3),
            "premium_review_calls_per_scenario": round(baseline_premium_calls / total, 3),
            "estimated_premium_chars": baseline_premium_chars,
            "results": baseline_results,
        },
        "experiment": {
            "scenario_protection_rate": round(experiment_protected / total, 3),
            "critical_failure_catch_rate": round(experiment_critical / critical_total, 3),
            "bounded_remediation_enforcement_rate": round(experiment_bounded / bounded_total, 3),
            "adjudication_applicability_rate": round(experiment_forum / forum_total, 3),
            "premium_review_calls_per_scenario": round(experiment_premium_calls / total, 3),
            "estimated_premium_chars": experiment_premium_chars,
            "results": experiment_results,
        },
        "delta": {
            "scenario_protection_gain": round((experiment_protected - baseline_protected) / total, 3),
            "critical_failure_catch_gain": round((experiment_critical - baseline_critical) / critical_total, 3),
            "bounded_remediation_gain": round((experiment_bounded - baseline_bounded) / bounded_total, 3),
            "adjudication_applicability_gain": round((experiment_forum - baseline_forum) / forum_total, 3),
            "premium_review_call_reduction": round((baseline_premium_calls - experiment_premium_calls) / total, 3),
            "estimated_premium_char_reduction": baseline_premium_chars - experiment_premium_chars,
        },
    }


def main() -> None:
    print(json.dumps(evaluate_replay_scenarios(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
