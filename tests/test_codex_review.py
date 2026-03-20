from dual_agents.cli import default_workflow_config
from dual_agents.codex_review import build_review_command, build_review_prompt


def test_review_prompt_mentions_review_only_default() -> None:
    prompt = build_review_prompt(default_workflow_config())
    assert "do not edit files unless the user explicitly asks" in prompt.lower()
    assert "delivery proof status" in prompt.lower()
    assert "treat \"local artifact exists\" and \"remote artifact delivered\" as different states" in prompt.lower()
    assert "workflow success as proof unless the run is bound" in prompt.lower()
    assert "review exactly one bounded decision per request" in prompt.lower()
    assert "if a review times out, narrow the packet" in prompt.lower()
    assert "internal reasoning text" in prompt.lower()
    assert "per-brand or per-item breakdown" in prompt.lower()
    assert "one bounded remediation cluster" in prompt.lower()
    assert "forum_adjudication" in prompt.lower()
    assert "moderator ruling" in prompt.lower()
    assert "missing launcher arguments" in prompt.lower()
    assert "unknown runtime schema" in prompt.lower()
    assert "stop report" in prompt.lower()
    assert "stop signal" in prompt.lower()
    assert "ad hoc python heredoc" in prompt.lower()
    assert "inspect schema, fix parser, rerun the same bounded analysis" in prompt.lower()
    assert "desktop/downloads" in prompt.lower()
    assert "absolute image path and use codex image handoff" in prompt.lower()
    assert "endpoint_preflight.py" in prompt
    assert "url/port errors" in prompt.lower()
    assert "preflight_stage.py" in prompt
    assert "require_worktree.py" in prompt
    assert "preflight fails and the workflow still attempts `git add`" in prompt.lower()
    assert "git add -a" in prompt.lower()
    assert "sse read timed out" in prompt.lower()


def test_review_command_starts_with_codex_exec() -> None:
    command = build_review_command(default_workflow_config())
    assert command[:2] == ["codex", "exec"]
