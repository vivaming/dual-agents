import json

from dual_agents.cli import default_workflow_config
from dual_agents.opencode_assets import build_agent_markdown, build_command_markdown, build_opencode_config


def test_build_command_mentions_dual_trigger() -> None:
    markdown = build_command_markdown(default_workflow_config())
    assert "/dual" in markdown
    assert "do not claim remote delivery from local success alone" in markdown.lower()
    assert "git log <target-branch> -1 --oneline" in markdown
    assert "remotely available, deployed, or notified" in markdown.lower()


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
    assert "--mode post-review" in agents["dual-coordinator.md"]
    assert "forum_adjudication" in agents["dual-coordinator.md"].lower()
    assert "--mode forum" in agents["dual-coordinator.md"]


def test_build_opencode_config_targets_zai_provider() -> None:
    config = default_workflow_config()
    rendered = build_opencode_config(config)
    payload = json.loads(rendered)
    assert payload["model"] == "zai/glm-5"
    assert payload["provider"]["zai"]["options"]["baseURL"] == "https://api.z.ai/api/coding/paas/v4/"
    assert payload["provider"]["zai"]["options"]["apiKey"] == "{env:GLM_API_KEY}"
