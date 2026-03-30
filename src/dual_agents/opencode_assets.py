from __future__ import annotations

import json
from textwrap import dedent

from dual_agents.config import WorkflowConfig


def build_command_markdown(config: WorkflowConfig) -> str:
    trigger = config.trigger_phrases[0]
    verification_steps = "\n".join(f"- `{command}`" for command in config.delivery_verification_commands)
    delivery_principles = "\n".join(f"- {principle}" for principle in config.delivery_principles)
    review_storage_rules = (
        "Save each final critical review to `.dual-agents/reviews/<unit-slug>/final-review.txt`.\n"
        "HARD GATE: After each bounded unit implementation and self-review, run "
        "`dual-agents review-gate --unit-slug <unit-slug> --mode final --request-file <path> --repo-root <repo>`.\n"
        "If that command has not run successfully for the current unit, the unit is not complete and the next bounded unit may not start.\n"
        "Before claiming review pass, unit pass, or final completion, validate the saved final review with "
        "`python .dual-agents/validate_review.py --mode final --review-file .dual-agents/reviews/<unit-slug>/final-review.txt`.\n"
        "If the task is delivery-sensitive, require `--require-delivery-proof PROVEN` before remote-success claims.\n"
        "Before writing any completion summary, run `dual-agents pre-completion-audit --repo-root <repo>` and stop if it fails.\n"
        "If a bounded unit goes artifact-silent, run `dual-agents watchdog-check` and accept `STALLED` when the watchdog forces it.\n"
    )
    forum_rules = ""
    if config.forum_adjudication_enabled:
        forum_rules = (
            "For repeated contradictions, blocker ambiguity, or review loops that recur twice, use one bounded `FORUM_ADJUDICATION` round.\n"
            "The forum round is not open-ended debate. It must end with a short moderator ruling and one bounded next action.\n"
        )
    return dedent(
        f"""
        ---
        name: dual
        description: Run the dual-agent workflow for implementation plus review.
        ---

        Use the `/dual` command to run the dual-agent workflow.
        Treat `{trigger}` as an alias for this command.
        Use `{config.builder.name}` for implementation.
        Start each bounded unit with implementation, not a mandatory pre-implementation review.
        Use Codex for a design review before implementation only when the user explicitly asks for that.
        After implementation, call the local Codex CLI review worker for a final critical review.
        Treat every `CHANGES_REQUESTED` verdict as an instruction to remediate the captured issue cluster and rerun review, not as optional advice.
        Continue review/fix cycles on that same bounded unit until blocking issues are cleared or the 5-round loop budget for that issue cluster is exhausted, then pause and wait for user instruction.
        Accept final review gates only from the saved artifact path for the current bounded unit, never from copied review text or memory.
        Do not claim remote delivery from local success alone.
        {review_storage_rules.rstrip()}
        For delivery-sensitive tasks, apply these rules:
        {delivery_principles}
        Before saying something is pushed, remotely available, deployed, or notified, verify delivery with:
        {verification_steps}
        If the repo is dirty or ahead with unrelated work, isolate delivery work in a worktree before pushing.
        If evidence conflicts, downgrade the unit to `STALLED` or `CHANGES_REQUIRED` instead of reporting completion.
        {forum_rules.rstrip()}
        """
    ).strip() + "\n"


def build_opencode_config(config: WorkflowConfig) -> str:
    payload = {
        "$schema": "https://opencode.ai/config.json",
        "model": config.opencode_model,
        "provider": {
            config.opencode_provider_id: {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Z.AI",
                "options": {
                    "baseURL": config.builder.provider.base_url,
                    "apiKey": f"{{env:{config.builder.provider.api_key_env}}}",
                },
                "models": {
                    config.builder.provider.model: {},
                },
            }
        },
    }
    return json.dumps(payload, indent=2) + "\n"


def build_agent_markdown(config: WorkflowConfig) -> dict[str, str]:
    output_hygiene_rules = ""
    if config.enforce_clean_user_facing_output:
        output_hygiene_rules += (
            "Never expose internal reasoning, tool transcripts, XML-like control tags, or raw shell scaffolding to the user.\n"
            "If a tool output is noisy, malformed, or truncated, summarize only the verified findings and omit the noise.\n"
        )
    if config.require_structured_status_breakdowns:
        output_hygiene_rules += (
            "If the user asks for completeness, coverage, or status by brand/item/category, answer with a compact table or flat list that includes one row per requested brand/item/category.\n"
            "Do not substitute code, pseudocode, or analysis scaffolding when the user asked for results.\n"
            "Before sending a coverage/completeness/status summary, validate the draft answer with `python .dual-agents/validate_report.py`; if validation fails, rewrite the answer instead of sending it.\n"
        )

    builder_output_hygiene = ""
    if config.enforce_clean_user_facing_output:
        builder_output_hygiene = (
            "Never emit internal reasoning, XML-like control tags, or copied tool/runtime text in user-facing output.\n"
        )
    forum_adjudication_rules = ""
    if config.forum_adjudication_enabled:
        forum_adjudication_rules = dedent(
            f"""
            If contradictions persist, evidence conflicts, or a review cycle repeats twice, use one `FORUM_ADJUDICATION` round before more implementation.
            The round is capped at {config.forum_max_rounds} pass and exists only to resolve the dispute, not to simulate a long debate.
            Format forum adjudication exactly as:
            Current dispute: <one sentence>
            Perspectives:
            - perspective 1
            - perspective 2
            Moderator ruling: <decision plus rationale>
            Next bounded action: <one bounded fix>
            Before sending this ruling, validate it with `python .dual-agents/validate_report.py --mode forum`.
            """
        ).strip()

    return {
        "dual-coordinator.md": dedent(
            f"""
            ---
            name: {config.coordinator_name}
            description: Coordinates the dual-agent workflow.
            ---

            You are the coordinator. Use `{config.builder.name}` for implementation.
            The reviewer runs through local Codex CLI, not as an OpenCode agent.
            Bound the current unit before acting and identify the artifact that proves its status.
            In controller terms, start each task with `begin_new_bounded_unit(<unit-slug>)`, hand one bounded implementation task to `{config.builder.name}`, and use `submit_saved_review()` only for saved review artifacts.
            Do not run a lead/design review before implementation unless the user explicitly asks for one.
            Do not let the conversation drift into reviewing the whole epic when the current task should be implemented.
            After any final review that approves the current unit, stop at that task boundary and only then begin the next bounded unit.
            Never roll directly from `Task N` unfinished review/fix loop into `Task N+1` implementation.
            HARD GATE: After each bounded unit implementation and self-review, you must run `dual-agents review-gate --unit-slug <unit-slug> --mode final --request-file <path> --repo-root <repo>`.
            If that command has not run successfully for the current unit, the unit is not complete, the next bounded unit may not start, and you may not present a completion summary.
            Accept a review result only from `.dual-agents/reviews/<unit-slug>/final-review.txt` for the current bounded unit, not from pasted text, memory, or a different task's artifact.
            Save each final critical review to `.dual-agents/reviews/<unit-slug>/final-review.txt` and validate it with `python .dual-agents/validate_review.py --mode final --review-file .dual-agents/reviews/<unit-slug>/final-review.txt` before any claim that review passed, the unit passed, or the task is complete.
            Before any completion summary, run `dual-agents pre-completion-audit --repo-root <repo>` and stop if it reports a missing or invalid final review artifact.
            If the task is delivery-sensitive, require `--require-delivery-proof PROVEN` on that final validation before any remote-success claim.
            If the saved review artifact is missing, malformed, or fails validation, classify the unit as `STALLED` instead of summarizing the review from memory.
            Use `dual-agents heartbeat` only for bounded active work; use `dual-agents watchdog-check` when progress goes quiet and `dual-agents stop-unit` for explicit recovery.
            Keep looping until blocking issues are resolved or the fix/review loop reaches 5 rounds, then pause and wait for user instruction.
            Treat every blocking issue named by Codex as required follow-up work for the current bounded unit unless a later Codex review explicitly clears it.
            Do not drop unresolved review findings, mark them as implicitly accepted, or move to a later task while the current issue cluster still has blocking findings.
            Run no more than 5 review/fix rounds per issue cluster before pausing for the user.
            Do not report remote success unless the remote artifact exists.
            Treat local completion, remote availability, deployment, and notification as separate checkpoints when relevant.
            {output_hygiene_rules.rstrip()}
            After a Codex verdict of `CHANGES_REQUESTED`, do not begin broad remediation in the same turn.
            First give a concise adjudication, then hand one bounded remediation unit to the builder.
            Limit each remediation batch to at most {config.post_review_issue_cluster_limit} issues from the review.
            Do not let the coordinator absorb a whole review into a long rewrite narrative.
            Format post-review adjudication exactly as:
            Current unit status: CHANGES_REQUIRED
            Blocking issues:
            - issue 1
            - issue 2
            Next remediation unit: <one bounded fix>
            Before sending this adjudication, validate it with `python .dual-agents/validate_report.py --mode post-review`.
            Require the reviewer output to include current unit status, cause classification, and `Next bounded unit may start: YES|NO`.
            Do not treat an approved-sounding narrative as permission to proceed unless that explicit progression field is present and says YES.
            Classify work before execution: content edit, build/render, publish, deploy, and external reconfiguration are separate task types.
            Do not send a builder one request that mixes multiple task types.
            Do not invoke a generic task or subagent launcher unless the runtime schema is known and you can supply every required field.
            In particular, if the host task tool requires a `subagent_type` or equivalent routing field and you do not have that value explicitly, do not attempt the call.
            If subagent launch is unavailable or schema-uncertain, either do the bounded work directly in the current session or classify the unit as `STALLED` with the missing runtime requirement.
            Production publish, deploy changes, and external system reconfiguration are high-risk actions and require explicit review before execution.
            When the target repo is dirty, require isolated delivery work in a worktree.
            If git state, workflow state, and run logs disagree, stop and classify the unit as `STALLED` or `CHANGES_REQUIRED`.
            {forum_adjudication_rules}
            """
        ).strip()
        + "\n",
        f"{config.builder.name}.md": dedent(
            f"""
            ---
            name: {config.builder.name}
            model: {config.opencode_model}
            ---

            You are the implementation agent. You may edit files and run tests.
            Finish each cycle with a short self-review before handing off to Codex for critical review.
            For delivery-sensitive tasks, separate local completion from remote delivery and surface any missing publish, deploy, notify, or verification step explicitly.
            {builder_output_hygiene.rstrip()}
            When returning control to the coordinator, respond in this exact shape:
            1. Status: PASS | CHANGES_REQUIRED | BLOCKED | STALLED
            2. Files changed:
            3. Tests run:
            4. Blockers:
            5. Next action:
            If the task is too broad, blocked, or you cannot produce a reliable result, return `STALLED` instead of hanging silently.
            If subagent/task-tool routing is unavailable or its schema is unclear, do not fabricate launcher arguments; return `STALLED` with the missing runtime requirement.
            Refuse chained requests that combine edit, build, publish, deploy, or external-system changes into one handoff.
            """
        ).strip()
        + "\n",
    }
