import json

from dual_agents.cli import default_workflow_config
from dual_agents.opencode_assets import build_agent_markdown, build_command_markdown, build_opencode_config


def test_build_command_mentions_dual_trigger() -> None:
    markdown = build_command_markdown(default_workflow_config())
    assert "/dual" in markdown
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
    assert "validate_review.py" in agents["dual-coordinator.md"]
    assert "do not begin broad remediation in the same turn" in agents["dual-coordinator.md"].lower()
    assert "before implementation starts on a new bounded unit" in agents["dual-coordinator.md"].lower()
    assert "--mode post-review" in agents["dual-coordinator.md"]
    assert "next bounded unit may start" in agents["dual-coordinator.md"].lower()
    assert "lead-review.txt" in agents["dual-coordinator.md"]
    assert "final-review.txt" in agents["dual-coordinator.md"]
    assert "forum_adjudication" in agents["dual-coordinator.md"].lower()
    assert "--mode forum" in agents["dual-coordinator.md"]
    assert "subagent_type" in agents["dual-coordinator.md"]
    assert "schema is known" in agents["dual-coordinator.md"].lower()
    assert "monitor_stop.py" in agents["dual-coordinator.md"]
    assert "spec_completeness_analyzer.py" in agents["dual-coordinator.md"]
    assert "endpoint_preflight.py" in agents["dual-coordinator.md"]
    assert "require_worktree.py" in agents["dual-coordinator.md"]
    assert "do not improvise a python heredoc" in agents["dual-coordinator.md"].lower()
    assert "inspect schema" in agents["dual-coordinator.md"].lower()
    assert "identify the exact target url" in agents["dual-coordinator.md"].lower()
    assert "preflight fails" in agents["dual-coordinator.md"].lower()
    assert "current model is glm-5" in agents["dual-coordinator.md"].lower()
    assert "analyze_image.py" in agents["dual-coordinator.md"]
    assert "stop signal:" in agents["dual-coordinator.md"].lower()
    assert "preflight_stage.py" in agents["dual-coordinator.md"]
    assert "git add -a" in agents["dual-coordinator.md"].lower()
    assert "do not attempt a narrower `git add`" in agents["dual-coordinator.md"].lower()
    assert "current workspace is not a linked worktree" in agents["dual-coordinator.md"].lower()
    assert "return `stalled`" in agents["glm-builder.md"].lower()
    assert "preflight_stage.py" in agents["glm-builder.md"]
    assert "require_worktree.py" in agents["glm-builder.md"]
    assert "do not write ad hoc python heredocs" in agents["glm-builder.md"].lower()
    assert "codex handoff" in agents["glm-builder.md"].lower()
    assert "do not proceed until `python .dual-agents/endpoint_preflight.py --url <target-url>` succeeds".lower() in agents["glm-builder.md"].lower()
    assert "do not run `git add` or `git commit` in the same session" in agents["glm-builder.md"].lower()


def test_build_opencode_config_targets_zai_provider() -> None:
    config = default_workflow_config()
    rendered = build_opencode_config(config)
    payload = json.loads(rendered)
    assert payload["model"] == "zai/glm-5"
    assert payload["provider"]["zai"]["options"]["baseURL"] == "https://api.z.ai/api/coding/paas/v4/"
    assert payload["provider"]["zai"]["options"]["apiKey"] == "{env:GLM_API_KEY}"
