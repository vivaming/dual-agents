from __future__ import annotations

from enum import Enum


class WorkflowStage(str, Enum):
    REQUEST_RECEIVED = "request_received"
    EPIC_DRAFT = "epic_draft"
    EPIC_REVIEW = "epic_review"
    IMPLEMENTATION = "implementation"
    SELF_REVIEW = "self_review"
    CRITICAL_REVIEW = "critical_review"
    ADJUDICATION = "adjudication"
    FORUM_ADJUDICATION = "forum_adjudication"
    DELIVERY_VERIFICATION = "delivery_verification"
    DEPLOY_READY = "deploy_ready"


def next_stage(stage: WorkflowStage, has_blocking_issues: bool = False) -> WorkflowStage:
    if stage == WorkflowStage.REQUEST_RECEIVED:
        return WorkflowStage.EPIC_DRAFT
    if stage == WorkflowStage.EPIC_DRAFT:
        return WorkflowStage.EPIC_REVIEW
    if stage == WorkflowStage.EPIC_REVIEW:
        return WorkflowStage.IMPLEMENTATION
    if stage == WorkflowStage.IMPLEMENTATION:
        return WorkflowStage.SELF_REVIEW
    if stage == WorkflowStage.SELF_REVIEW:
        return WorkflowStage.CRITICAL_REVIEW
    if stage == WorkflowStage.CRITICAL_REVIEW:
        return WorkflowStage.IMPLEMENTATION if has_blocking_issues else WorkflowStage.ADJUDICATION
    if stage == WorkflowStage.ADJUDICATION:
        return WorkflowStage.DELIVERY_VERIFICATION
    if stage == WorkflowStage.FORUM_ADJUDICATION:
        return WorkflowStage.IMPLEMENTATION
    if stage == WorkflowStage.DELIVERY_VERIFICATION:
        return WorkflowStage.DEPLOY_READY
    return WorkflowStage.DEPLOY_READY
