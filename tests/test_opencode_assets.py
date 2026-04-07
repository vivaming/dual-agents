import json

from dual_agents.cli import default_workflow_config
from dual_agents.opencode_assets import build_agent_markdown, build_command_markdown, build_opencode_config


def test_build_command_mentions_dual_trigger() -> None:
    markdown = build_command_markdown(default_workflow_config())
    assert "/dual" in markdown
    assert "start each bounded unit by running `dual-agents start-unit`" in markdown.lower()
    assert "auto-detects implementation vs pre-implementation review" in markdown.lower()
    assert "if `dual-agents start-unit` chooses `implementation`" in markdown.lower()
    assert "if it chooses `epic_review`" in markdown.lower()
    assert "after implementation, call the local codex cli review worker" in markdown.lower()
    assert "after a bounded unit passes final review" not in markdown.lower()
    assert "continue review/fix cycles on that same bounded unit" in markdown.lower()
    assert "accept final review gates only from the saved artifact path" in markdown.lower()
    assert "do not claim remote delivery from local success alone" in markdown.lower()
    assert "git log <target-branch> -1 --oneline" in markdown
    assert "remotely available, deployed, or notified" in markdown.lower()
    assert "validate_review.py" in markdown
    assert "final-review.txt" in markdown
    assert "submit-review-artifact" in markdown
    assert "previously produced by codex cli" in markdown.lower()
    assert "never use `submit-review-artifact` for a coordinator-authored" in markdown.lower()
    assert "watchdog-check" in markdown
    assert "hard gate" in markdown.lower()
    assert "pre-completion-audit" in markdown


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
    assert "before doing substantive work on a new bounded unit, run `dual-agents start-unit" in agents["dual-coordinator.md"].lower()
    assert "read the returned json" in agents["dual-coordinator.md"].lower()
    assert "decision_reason" in agents["dual-coordinator.md"]
    assert "do not override an `implementation` start just because an epic exists" in agents["dual-coordinator.md"].lower()
    assert "activate a lead/design review only when the classifier or the user explicitly points to planning/review intent" in agents["dual-coordinator.md"].lower()
    assert "drift into reviewing the whole epic" in agents["dual-coordinator.md"].lower()
    assert "hand one bounded implementation task" in agents["dual-coordinator.md"].lower()
    assert "begin_new_bounded_unit(<unit-slug>)" in agents["dual-coordinator.md"]
    assert "submit_saved_review()" in agents["dual-coordinator.md"]
    assert "never roll directly from `task n` unfinished review/fix loop into `task n+1`" in agents["dual-coordinator.md"].lower()
    assert "accept a review result only from `.dual-agents/reviews/<unit-slug>/final-review.txt`" in agents["dual-coordinator.md"].lower()
    assert "or a review that you wrote yourself" in agents["dual-coordinator.md"].lower()
    assert "do not drop unresolved review findings" in agents["dual-coordinator.md"].lower()
    assert "run no more than 5 review/fix rounds per issue cluster before pausing for the user" in agents["dual-coordinator.md"].lower()
    assert "next bounded unit may start" in agents["dual-coordinator.md"].lower()
    assert "--mode post-review" in agents["dual-coordinator.md"]
    assert "forum_adjudication" in agents["dual-coordinator.md"].lower()
    assert "--mode forum" in agents["dual-coordinator.md"]
    assert "validate_review.py" in agents["dual-coordinator.md"]
    assert "final-review.txt" in agents["dual-coordinator.md"]
    assert "subagent_type" in agents["dual-coordinator.md"]
    assert "schema is known" in agents["dual-coordinator.md"].lower()
    assert "heartbeat" in agents["dual-coordinator.md"].lower()
    assert "stop-unit" in agents["dual-coordinator.md"].lower()
    assert "submit-review-artifact" in agents["dual-coordinator.md"]
    assert "never author a review file yourself and then feed it to `dual-agents submit-review-artifact`" in agents["dual-coordinator.md"].lower()
    assert "pre-completion-audit" in agents["dual-coordinator.md"]
    assert "hard gate" in agents["dual-coordinator.md"].lower()
    assert "return `stalled`" in agents["glm-builder.md"].lower()


def test_build_opencode_config_targets_zai_provider() -> None:
    config = default_workflow_config()
    rendered = build_opencode_config(config)
    payload = json.loads(rendered)
    assert payload["model"] == "zai/glm-5.1"
    assert payload["provider"]["zai"]["options"]["baseURL"] == "https://api.z.ai/api/coding/paas/v4/"
    assert payload["provider"]["zai"]["options"]["apiKey"] == "{env:GLM_API_KEY}"
