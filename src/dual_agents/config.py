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
    command: list[str] = Field(default_factory=lambda: ["codex", "exec"])
    mode: Literal["review_only", "review_then_edit_on_request"] = "review_then_edit_on_request"
    prompt: str = Field(min_length=1)


class WorkflowConfig(BaseModel):
    trigger_phrases: list[str] = Field(default_factory=lambda: ["sort it out with dual agent workflow"])
    builder: AgentConfig
    reviewer: ReviewerConfig
    coordinator_name: str = "dual-coordinator"
    opencode_provider_id: str = "zai"
    opencode_model: str = "zai/glm-5"
    delivery_verification_commands: list[str] = Field(default_factory=list)
    delivery_principles: list[str] = Field(default_factory=list)
    review_packet_max_files: int = 5
    review_packet_target_max_chars: int = 4000
    review_packet_timeout_max_attempts: int = 3
    enforce_clean_user_facing_output: bool = True
    require_structured_status_breakdowns: bool = True
    post_review_issue_cluster_limit: int = 3
    enforce_post_review_adjudication_contract: bool = True
