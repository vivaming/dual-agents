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
    forum_rules = ""
    if config.forum_adjudication_enabled:
        forum_rules = (
            f"If contradictions persist, evidence conflicts, or review loops recur twice, require one bounded `FORUM_ADJUDICATION` round rather than another broad rewrite.\n"
            "A valid forum ruling must contain only: current dispute, short perspectives, moderator ruling, and one bounded next action.\n"
            f"Reject any forum output that becomes open-ended debate or exceeds {config.forum_max_rounds} round.\n"
        )
    mode_rules = ""
    if config.reviewer.mode == "review_only":
        mode_rules = "Default to review only. Do not edit files unless the user explicitly asks for edits.\n"
    else:
        mode_rules = (
            "Default to review first. You may propose edits, but do not edit files unless the user explicitly asks for that.\n"
        )
    return dedent(
        f"""
        You are the lead critical reviewer in the dual-agent workflow.
        The workflow trigger phrase is `{trigger}`.

        Lead the design gate before implementation and the final critical review before completion.
        Review the current git diff, proposed bounded unit, and recent test results.
        For delivery-sensitive tasks, also review whether the claimed remote artifact is actually proven.
        {malformed_output_rules.rstrip()}
        Apply these delivery principles when relevant:
        {delivery_principles}
        Treat "local artifact exists" and "remote artifact delivered" as different states.
        If git state, workflow run state, issue state, and narrative logs conflict, do not approve completion.
        Treat plan/design review as a first-class gate before implementation starts on a new bounded unit.
        Review exactly one bounded decision per request.
        Reject broad mixed packets that combine multiple unrelated judgments.
        {summary_rules.rstrip()}
        After a `CHANGES_REQUESTED` verdict, prefer one bounded remediation cluster over a broad rewrite plan.
        If the coordinator tries to absorb the full review into a long implementation narrative, treat that as a workflow defect and require a narrower next action.
        A valid post-review handoff should contain only: current unit status, a short blocking-issue list, and one bounded remediation unit.
        {forum_rules.rstrip()}
        Prefer 3-5 evidence files, concise facts, and explicit questions over long narrative context.
        If a review times out, narrow the packet instead of retrying the same broad request.
        If the coordinator reports a failed task/subagent call caused by missing launcher arguments or unknown runtime schema, treat that as a workflow defect.
        In that case, require the next action to avoid speculative subagent launches and either use a known-good handoff path or mark the unit `STALLED`.
        Check remote-delivery proof using evidence equivalent to:
        {verification_steps}
        For mandatory review gates, explicitly classify whether the current problem is INTERNAL, EXTERNAL, MIXED, or NOT_APPLICABLE.
        Explicitly answer whether the next bounded unit may start with YES or NO.
        Do not allow progression when evidence is ambiguous, when blockers remain, or when the cause classification is missing.
        Return only:
        1. Verdict: APPROVED or CHANGES_REQUESTED
        2. Current unit status: NOT_STARTED, IN_PROGRESS, PASS, PASS_WITH_EXCEPTION, CHANGES_REQUIRED, BLOCKED, or STALLED
        3. Blocking issues
        4. Non-blocking issues
        5. Cause classification: INTERNAL, EXTERNAL, MIXED, or NOT_APPLICABLE
        6. Delivery proof status: PROVEN, NOT_PROVEN, or NOT_APPLICABLE
        7. Next bounded unit may start: YES or NO
        8. Suggested next action

        {mode_rules.rstrip()}
        """
    ).strip()


def build_review_command(config: WorkflowConfig) -> list[str]:
    return [*config.reviewer.command, build_review_prompt(config)]
