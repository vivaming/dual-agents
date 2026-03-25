import pytest

from dual_agents.controller import (
    BuilderVerdict,
    CauseClassification,
    DecisionCategory,
    DeliveryProofStatus,
    HighRiskAction,
    ProgressionDecision,
    ReviewUnitStatus,
    ReviewVerdict,
    TaskType,
    WorkflowController,
    WorkflowViolation,
    should_enter_forum_adjudication,
    requires_premium_review,
    validate_forum_ruling,
    contains_internal_leak,
    build_remediation_issue_cluster,
    is_bounded_builder_task,
    parse_builder_result,
    parse_review_result,
    requires_critical_review,
    validate_post_review_adjudication,
    validate_user_facing_report,
)
from dual_agents.workflow import WorkflowStage


VALID_REVIEW = """
1. Verdict: APPROVED
2. Current unit status: PASS
3. Blocking issues: None
4. Non-blocking issues:
- tighten naming
5. Cause classification: NOT_APPLICABLE
6. Delivery proof status: NOT_PROVEN
7. Next bounded unit may start: YES
8. Suggested next action: Verify the remote artifact before completion.
"""

VALID_BUILDER_RESULT = """
1. Status: PASS
2. Files changed:
- scripts/extract_full_catalog.py
3. Tests run:
- python -m py_compile scripts/extract_full_catalog.py
4. Blockers: None
5. Next action: Hand off for self-review.
"""


def test_parse_review_result_accepts_structured_output() -> None:
    result = parse_review_result(VALID_REVIEW)
    assert result.verdict == ReviewVerdict.APPROVED
    assert result.current_unit_status == ReviewUnitStatus.PASS
    assert result.blocking_issues == ()
    assert result.non_blocking_issues == ("tighten naming",)
    assert result.cause_classification == CauseClassification.NOT_APPLICABLE
    assert result.delivery_proof_status == DeliveryProofStatus.NOT_PROVEN
    assert result.next_bounded_unit_may_start == ProgressionDecision.YES


def test_parse_review_result_rejects_missing_field() -> None:
    with pytest.raises(WorkflowViolation):
        parse_review_result("1. Verdict: APPROVED")


def test_controller_routes_changes_requested_back_to_implementation() -> None:
    controller = WorkflowController()
    controller.stage = WorkflowStage.CRITICAL_REVIEW
    review = controller.submit_review(
        """
1. Verdict: CHANGES_REQUESTED
2. Current unit status: CHANGES_REQUIRED
3. Blocking issues:
- parser output malformed
4. Non-blocking issues: None
5. Cause classification: INTERNAL
6. Delivery proof status: NOT_APPLICABLE
7. Next bounded unit may start: NO
8. Suggested next action: Fix the malformed output and rerun review.
"""
    )
    assert review.has_blocking_issues is True
    assert controller.stage == WorkflowStage.IMPLEMENTATION


def test_delivery_sensitive_controller_requires_explicit_proof() -> None:
    controller = WorkflowController(delivery_sensitive=True)
    controller.stage = WorkflowStage.ADJUDICATION
    assert controller.advance() == WorkflowStage.DELIVERY_VERIFICATION
    with pytest.raises(WorkflowViolation):
        controller.verify_delivery(artifact_proven=False, evidence_consistent=True)
    assert controller.verify_delivery(artifact_proven=True, evidence_consistent=True) == WorkflowStage.DEPLOY_READY


def test_non_delivery_sensitive_controller_skips_delivery_stage() -> None:
    controller = WorkflowController(delivery_sensitive=False)
    controller.stage = WorkflowStage.ADJUDICATION
    assert controller.advance() == WorkflowStage.DEPLOY_READY


def test_new_tasks_require_critical_review() -> None:
    assert requires_critical_review(decision_category=DecisionCategory.NEW_TASKS) is True


def test_partial_status_requires_critical_review_even_for_ordinary_work() -> None:
    assert (
        requires_critical_review(
            decision_category=DecisionCategory.ORDINARY_IMPLEMENTATION,
            current_unit_status="PARTIAL",
        )
        is True
    )


def test_controller_blocks_epic_progress_when_review_is_required() -> None:
    controller = WorkflowController()
    controller.stage = WorkflowStage.EPIC_REVIEW
    with pytest.raises(WorkflowViolation):
        controller.advance()


def test_epic_review_result_can_start_implementation() -> None:
    controller = WorkflowController()
    controller.stage = WorkflowStage.EPIC_REVIEW
    review = controller.submit_review(VALID_REVIEW)
    assert review.may_start_next_unit is True
    assert controller.stage == WorkflowStage.IMPLEMENTATION


def test_epic_review_with_no_progression_loops_back_to_epic_draft() -> None:
    controller = WorkflowController()
    controller.stage = WorkflowStage.EPIC_REVIEW
    review = controller.submit_review(
        """
1. Verdict: CHANGES_REQUESTED
2. Current unit status: CHANGES_REQUIRED
3. Blocking issues:
- clarify acceptance criteria
4. Non-blocking issues: None
5. Cause classification: INTERNAL
6. Delivery proof status: NOT_APPLICABLE
7. Next bounded unit may start: NO
8. Suggested next action: Narrow the unit and rerun lead review.
"""
    )
    assert review.may_start_next_unit is False
    assert controller.stage == WorkflowStage.EPIC_DRAFT


def test_controller_clears_review_requirement_after_valid_review() -> None:
    controller = WorkflowController()
    controller.flag_decision_for_review(decision_category=DecisionCategory.NEW_TASKS)
    controller.stage = WorkflowStage.CRITICAL_REVIEW
    controller.submit_review(VALID_REVIEW)
    assert controller.critical_review_required is False


def test_parse_builder_result_accepts_structured_output() -> None:
    result = parse_builder_result(VALID_BUILDER_RESULT)
    assert result.verdict == BuilderVerdict.PASS
    assert result.files_changed == ("scripts/extract_full_catalog.py",)
    assert result.tests_run == ("python -m py_compile scripts/extract_full_catalog.py",)


def test_controller_blocks_advancing_while_builder_handoff_is_active() -> None:
    controller = WorkflowController()
    controller.stage = WorkflowStage.IMPLEMENTATION
    controller.start_builder_handoff("Fix syntax in extraction script.", task_types=(TaskType.SCRIPT_FIX,))
    with pytest.raises(WorkflowViolation):
        controller.advance()


def test_controller_accepts_valid_builder_result_and_clears_handoff() -> None:
    controller = WorkflowController()
    controller.stage = WorkflowStage.IMPLEMENTATION
    controller.start_builder_handoff("Fix syntax in extraction script.", task_types=(TaskType.SCRIPT_FIX,))
    result = controller.submit_builder_result(VALID_BUILDER_RESULT)
    assert result.verdict == BuilderVerdict.PASS
    assert controller.builder_handoff_active is False


def test_controller_marks_builder_stalled_and_requires_recovery() -> None:
    controller = WorkflowController()
    controller.stage = WorkflowStage.IMPLEMENTATION
    controller.start_builder_handoff("Fix syntax in extraction script.", task_types=(TaskType.SCRIPT_FIX,))
    with pytest.raises(WorkflowViolation):
        controller.mark_builder_stalled("No structured builder response received.")
    assert controller.builder_handoff_active is False
    assert controller.last_builder_result is not None
    assert controller.last_builder_result.verdict == BuilderVerdict.STALLED


def test_bounded_builder_task_rejects_chained_request_text() -> None:
    assert is_bounded_builder_task("Create HTML and publish to prod then reconfigure GSC") is False


def test_builder_handoff_requires_exactly_one_task_type() -> None:
    controller = WorkflowController()
    controller.stage = WorkflowStage.IMPLEMENTATION
    with pytest.raises(WorkflowViolation):
        controller.start_builder_handoff(
            "Create HTML.",
            task_types=(TaskType.BUILD_RENDER, TaskType.PUBLISH),
        )


def test_high_risk_actions_require_explicit_review_before_builder_execution() -> None:
    controller = WorkflowController()
    controller.stage = WorkflowStage.IMPLEMENTATION
    with pytest.raises(WorkflowViolation):
        controller.start_builder_handoff(
            "Publish the blog post.",
            task_types=(TaskType.PUBLISH,),
            high_risk_actions=(HighRiskAction.PRODUCTION_PUBLISH,),
        )


def test_empty_builder_output_is_converted_to_stalled_result() -> None:
    controller = WorkflowController()
    controller.stage = WorkflowStage.IMPLEMENTATION
    controller.start_builder_handoff("Create HTML.", task_types=(TaskType.BUILD_RENDER,))
    result = controller.submit_builder_result("   ")
    assert result.verdict == BuilderVerdict.STALLED
    assert controller.builder_handoff_active is False


def test_contains_internal_leak_flags_reasoning_and_control_tags() -> None:
    assert contains_internal_leak("Thinking: let me check the file") is True
    assert contains_internal_leak("<parameter name=\"x\">") is True
    assert contains_internal_leak("Brand  Coverage\nTENWAYS 100%") is False


def test_validate_user_facing_report_rejects_internal_leak() -> None:
    with pytest.raises(WorkflowViolation):
        validate_user_facing_report("Thinking: analyze output first")


def test_validate_user_facing_report_requires_requested_terms() -> None:
    with pytest.raises(WorkflowViolation):
        validate_user_facing_report("Affiliate only summary", required_terms=("Official",))


def test_validate_user_facing_report_accepts_clean_brand_summary() -> None:
    report = validate_user_facing_report(
        "Brand  Coverage\nTenways 100%\nAventon 95%\nOfficial brands included",
        required_terms=("Tenways", "Official"),
    )
    assert "Tenways 100%" in report


def test_build_remediation_issue_cluster_limits_scope() -> None:
    cluster = build_remediation_issue_cluster(
        ("issue 1", "issue 2", "issue 3", "issue 4"),
        max_items=3,
    )
    assert cluster == ("issue 1", "issue 2", "issue 3")


def test_validate_post_review_adjudication_accepts_bounded_format() -> None:
    result = validate_post_review_adjudication(
        "Current unit status: CHANGES_REQUIRED\n"
        "Blocking issues:\n"
        "- issue 1\n"
        "- issue 2\n"
        "Next remediation unit: add provenance section"
    )
    assert "Next remediation unit:" in result


def test_validate_post_review_adjudication_rejects_missing_labels() -> None:
    with pytest.raises(WorkflowViolation):
        validate_post_review_adjudication("Blocking issues:\n- issue 1")


def test_validate_post_review_adjudication_rejects_too_many_issues() -> None:
    with pytest.raises(WorkflowViolation):
        validate_post_review_adjudication(
            "Current unit status: CHANGES_REQUIRED\n"
            "Blocking issues:\n"
            "- issue 1\n"
            "- issue 2\n"
            "- issue 3\n"
            "- issue 4\n"
            "Next remediation unit: fix one thing"
        )


def test_forum_adjudication_trigger_requires_real_conflict_signal() -> None:
    assert (
        should_enter_forum_adjudication(
            repeated_review_cycles=2,
            conflicting_evidence=False,
            blocker_ambiguity=False,
            forum_enabled=True,
        )
        is True
    )
    assert (
        should_enter_forum_adjudication(
            repeated_review_cycles=0,
            conflicting_evidence=False,
            blocker_ambiguity=False,
            forum_enabled=True,
        )
        is False
    )


def test_requires_premium_review_returns_true_when_optimization_disabled() -> None:
    assert (
        requires_premium_review(
            premium_optimize_enabled=False,
            repeated_review_cycles=0,
        )
        is True
    )


def test_requires_premium_review_keeps_low_risk_ordinary_units_off_premium() -> None:
    assert (
        requires_premium_review(
            premium_optimize_enabled=True,
            repeated_review_cycles=0,
            conflicting_evidence=False,
            delivery_sensitive=False,
            high_risk_actions=(),
        )
        is False
    )


def test_requires_premium_review_escalates_high_risk_and_repeated_loops() -> None:
    assert (
        requires_premium_review(
            premium_optimize_enabled=True,
            high_risk_actions=(HighRiskAction.PRODUCTION_PUBLISH,),
        )
        is True
    )
    assert (
        requires_premium_review(
            premium_optimize_enabled=True,
            repeated_review_cycles=2,
        )
        is True
    )


def test_validate_forum_ruling_accepts_bounded_contract() -> None:
    ruling = validate_forum_ruling(
        """
Current dispute: The feed and page disagree on speed.
Perspectives:
- Feed value is structured.
- Page text may be stale.
Moderator ruling: Hold promotion until variant ownership is checked.
Next bounded action: Add variant-safety checks for max_speed_mph.
"""
    )
    assert "Moderator ruling:" in ruling


def test_validate_forum_ruling_rejects_excessive_perspectives() -> None:
    with pytest.raises(WorkflowViolation):
        validate_forum_ruling(
            """
Current dispute: The feed and page disagree on speed.
Perspectives:
- one
- two
- three
- four
Moderator ruling: Hold promotion until variant ownership is checked.
Next bounded action: Add variant-safety checks for max_speed_mph.
"""
        )
