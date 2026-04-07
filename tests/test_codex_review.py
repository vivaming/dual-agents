from dual_agents.cli import default_workflow_config
from dual_agents.codex_review import build_review_command, build_review_prompt


def test_review_prompt_mentions_review_only_default() -> None:
    prompt = build_review_prompt(default_workflow_config())
    assert "do not edit files unless the user explicitly asks" in prompt.lower()
    assert "default to post-implementation critical review" in prompt.lower()
    assert "only perform a pre-implementation design review when the user explicitly asks for one" in prompt.lower()
    assert "when handling that optional design review" in prompt.lower()
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
    assert "cause classification" in prompt.lower()
    assert "next bounded unit may start" in prompt.lower()
    assert "do not treat that approval as blanket permission to skip unfinished remediation" in prompt.lower()
    assert "until all blocking issues in the cluster are resolved or the workflow hits the 5-round loop cap" in prompt.lower()
    assert "must rely on the saved artifact itself" in prompt.lower()
    assert "do not return `changes_requested` solely because the final review artifact does not exist yet" in prompt.lower()
    assert "3. blocking issues:" in prompt.lower()
    assert "4. non-blocking issues:" in prompt.lower()


def test_review_command_starts_with_codex_exec() -> None:
    command = build_review_command(default_workflow_config())
    assert command[:4] == ["codex", "exec", "--model", "gpt-5.4"]
