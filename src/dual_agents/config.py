from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    name: str
    model: str
    base_url: str | None = None
    api_key_env: str | None = None


class AgentConfig(BaseModel):
    name: str
    provider: ProviderConfig
    role: str
    can_edit: bool = False
    prompt: str = Field(min_length=1)


class ReviewerConfig(BaseModel):
    name: str = "codex-reviewer"
    command: list[str] = Field(default_factory=lambda: ["codex", "exec", "--model", "gpt-5.4"])
    mode: Literal["review_only", "review_then_edit_on_request"] = "review_then_edit_on_request"
    prompt: str = Field(min_length=1)


class WorkflowConfig(BaseModel):
    trigger_phrases: list[str] = Field(default_factory=lambda: ["sort it out with dual agent workflow"])
    builder: AgentConfig
    reviewer: ReviewerConfig
    coordinator_name: str = "dual-coordinator"
    opencode_provider_id: str = "zai"
    opencode_model: str = "zai/glm-5.1"
    delivery_verification_commands: list[str] = Field(default_factory=list)
    delivery_principles: list[str] = Field(default_factory=list)
    review_packet_max_files: int = 5
    review_packet_target_max_chars: int = 4000
    review_packet_timeout_max_attempts: int = 3
    enforce_clean_user_facing_output: bool = True
    require_structured_status_breakdowns: bool = True
    post_review_issue_cluster_limit: int = 3
    enforce_post_review_adjudication_contract: bool = True
    forum_adjudication_enabled: bool = False
    forum_trigger_on_conflicting_evidence: bool = True
    forum_trigger_on_repeated_review_cycles: bool = True
    forum_max_rounds: int = 1
    premium_review_optimize_enabled: bool = False
    premium_review_on_new_tasks: bool = True
    premium_review_on_task_sequence_change: bool = True
    premium_review_on_high_risk_actions: bool = True
    premium_review_on_conflicting_evidence: bool = True
    premium_review_on_repeated_review_cycles: int = 2
    premium_review_on_delivery_sensitive: bool = True
