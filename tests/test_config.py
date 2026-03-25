import pytest
from pydantic import ValidationError

from dual_agents.cli import default_workflow_config
from dual_agents.config import ProviderConfig, ReviewerConfig


def test_provider_config_requires_model() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(name="glm")


def test_reviewer_defaults_to_codex_exec_with_gpt_5_4() -> None:
    reviewer = ReviewerConfig(prompt="Review only.")
    assert reviewer.command == ["codex", "exec", "--model", "gpt-5.4"]


def test_default_workflow_enables_clean_output_and_structured_breakdowns() -> None:
    config = default_workflow_config()
    assert config.enforce_clean_user_facing_output is True
    assert config.require_structured_status_breakdowns is True
    assert config.post_review_issue_cluster_limit == 3
    assert config.enforce_post_review_adjudication_contract is True
    assert config.premium_review_optimize_enabled is True
    assert config.premium_review_on_repeated_review_cycles == 2
    assert config.forum_adjudication_enabled is True
    assert config.forum_max_rounds == 1
