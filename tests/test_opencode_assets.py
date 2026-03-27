import json

from dual_agents.cli import default_workflow_config
from dual_agents.opencode_assets import build_agent_markdown, build_command_markdown, build_opencode_config


def test_build_command_mentions_dual_trigger() -> None:
    markdown = build_command_markdown(default_workflow_config())
    assert "/dual" in markdown
    assert "lead-review design gate" in markdown.lower()
    assert "do not claim remote delivery from local success alone" in markdown.lower()
    assert "git log <target-branch> -1 --oneline" in markdown
    assert "remotely available, deployed, or notified" in markdown.lower()
    assert "validate_review.py" in markdown
    assert "lead-review.txt" in markdown
    assert "final-review.txt" in markdown


def test_build_agent_markdown_contains_expected_agents() -> None:
    config = default_workflow_config()
    agents = build_agent_markdown(config)
    assert "glm-builder.md" in agents
    assert "dual-coordinator.md" in agents
    assert "do not report remote success unless the remote artifact exists" in agents["dual-coordinator.md"].lower()
    assert "publish, deploy, notify, or verification" in agents["glm-builder.md"].lower()
    assert "never expose internal reasoning" in agents["dual-coordinator.md"].lower()
    assert "one row per requested brand" in agents["dual-coordinator.md"].lower()
    assert "validate_report.py" in agents["dual-coordinator.md"]
    assert "do not begin broad remediation in the same turn" in agents["dual-coordinator.md"].lower()
    assert "before implementation starts on a new bounded unit" in agents["dual-coordinator.md"].lower()
    assert "next bounded unit may start" in agents["dual-coordinator.md"].lower()
    assert "--mode post-review" in agents["dual-coordinator.md"]
    assert "forum_adjudication" in agents["dual-coordinator.md"].lower()
    assert "--mode forum" in agents["dual-coordinator.md"]
    assert "validate_review.py" in agents["dual-coordinator.md"]
    assert "lead-review.txt" in agents["dual-coordinator.md"]
    assert "final-review.txt" in agents["dual-coordinator.md"]
    assert "subagent_type" in agents["dual-coordinator.md"]
    assert "schema is known" in agents["dual-coordinator.md"].lower()
    assert "return `stalled`" in agents["glm-builder.md"].lower()


def test_build_opencode_config_targets_zai_provider() -> None:
    config = default_workflow_config()
    rendered = build_opencode_config(config)
    payload = json.loads(rendered)
    assert payload["model"] == "zai/glm-4-turbo"
    assert payload["provider"]["zai"]["options"]["baseURL"] == "https://api.z.ai/api/coding/paas/v4/"
    assert payload["provider"]["zai"]["options"]["apiKey"] == "{env:GLM_API_KEY}"
