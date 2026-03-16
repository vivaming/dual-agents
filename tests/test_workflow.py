from dual_agents.workflow import WorkflowStage, next_stage


def test_workflow_loops_back_on_blocking_review() -> None:
    assert next_stage(WorkflowStage.CRITICAL_REVIEW, has_blocking_issues=True) == WorkflowStage.IMPLEMENTATION


def test_workflow_requires_delivery_verification_before_deploy_ready() -> None:
    assert next_stage(WorkflowStage.ADJUDICATION) == WorkflowStage.DELIVERY_VERIFICATION
    assert next_stage(WorkflowStage.DELIVERY_VERIFICATION) == WorkflowStage.DEPLOY_READY
