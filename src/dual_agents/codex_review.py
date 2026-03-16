from __future__ import annotations

from textwrap import dedent

from dual_agents.config import WorkflowConfig


def build_review_prompt(config: WorkflowConfig) -> str:
    trigger = config.trigger_phrases[0]
    verification_steps = "\n".join(f"- {command}" for command in config.delivery_verification_commands)
    delivery_principles = "\n".join(f"- {principle}" for principle in config.delivery_principles)
    malformed_output_rules = ""
    if config.enforce_clean_user_facing_output:
        malformed_output_rules = (
            "If the coordinator or builder output contains internal reasoning text, control tags, or raw tool transcript fragments, treat that as malformed output and request a clean rerun.\n"
        )
    summary_rules = ""
    if config.require_structured_status_breakdowns:
        summary_rules = (
            "When the requested result is a coverage/completeness/status summary, require the response to contain the requested per-brand or per-item breakdown instead of code or analysis scaffolding.\n"
        )
    return dedent(
        f"""
        You are the critical reviewer in the dual-agent workflow.
        The workflow trigger phrase is `{trigger}`.

        Review the current git diff and recent test results.
        For delivery-sensitive tasks, also review whether the claimed remote artifact is actually proven.
        {malformed_output_rules.rstrip()}
        Apply these delivery principles when relevant:
        {delivery_principles}
        Treat "local artifact exists" and "remote artifact delivered" as different states.
        If git state, workflow run state, issue state, and narrative logs conflict, do not approve completion.
        Review exactly one bounded decision per request.
        Reject broad mixed packets that combine multiple unrelated judgments.
        {summary_rules.rstrip()}
        After a `CHANGES_REQUESTED` verdict, prefer one bounded remediation cluster over a broad rewrite plan.
        If the coordinator tries to absorb the full review into a long implementation narrative, treat that as a workflow defect and require a narrower next action.
        A valid post-review handoff should contain only: current unit status, a short blocking-issue list, and one bounded remediation unit.
        Prefer 3-5 evidence files, concise facts, and explicit questions over long narrative context.
        If a review times out, narrow the packet instead of retrying the same broad request.
        Check remote-delivery proof using evidence equivalent to:
        {verification_steps}
        Return only:
        1. Verdict: APPROVED or CHANGES_REQUESTED
        2. Blocking issues
        3. Non-blocking issues
        4. Delivery proof status: PROVEN, NOT_PROVEN, or NOT_APPLICABLE
        5. Suggested next action

        Default to review only. You may propose edits, but do not edit files unless the user explicitly asks for that.
        """
    ).strip()


def build_review_command(config: WorkflowConfig) -> list[str]:
    return [*config.reviewer.command, build_review_prompt(config)]
