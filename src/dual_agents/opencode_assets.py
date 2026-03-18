from __future__ import annotations

import json
from textwrap import dedent

from dual_agents.config import WorkflowConfig


def build_command_markdown(config: WorkflowConfig) -> str:
    trigger = config.trigger_phrases[0]
    verification_steps = "\n".join(f"- `{command}`" for command in config.delivery_verification_commands)
    delivery_principles = "\n".join(f"- {principle}" for principle in config.delivery_principles)
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
        After implementation, call the local Codex CLI review worker and loop until blocking issues are resolved.
        Do not claim remote delivery from local success alone.
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
            Keep looping until blocking issues are resolved.
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
            If the workflow pauses, degrades, or emits repeated malformed tool calls, save a stop report before retrying.
            For spec completeness or bounded unit analysis, use the fixed analyzer only: `python .dual-agents/spec_completeness_analyzer.py --data-root data --brand-set affiliate --brand-set official`.
            The analyzer may read only `data/<brand>/coverage_report.json` files. Do not improvise a Python heredoc, ad hoc inline script, or alternate file source for completeness analysis.
            If completeness or bounded unit analysis emits a traceback, syntax error, or parser exception, stop immediately and produce a stop report instead of trying a second analysis path.
            After an analysis traceback, recovery is limited to exactly these steps:
            1. inspect schema
            2. fix parser
            3. rerun the same bounded analysis
            Do not jump from a failed analysis into another pilot, rollout step, or unrelated task.
            Format stop reports exactly as:
            Current unit: <bounded unit>
            Stop signal: <category>
            Matched categories: <comma-separated categories>
            Evidence:
            - evidence line
            Next recovery step: <single recovery step>
            Use `python .dual-agents/monitor_stop.py --transcript-file <path>` to classify the transcript snippet before continuing.
            Classify work before execution: content edit, build/render, publish, deploy, and external reconfiguration are separate task types.
            Do not send a builder one request that mixes multiple task types.
            Do not invoke a generic task or subagent launcher unless the runtime schema is known and you can supply every required field.
            In particular, if the host task tool requires a `subagent_type` or equivalent routing field and you do not have that value explicitly, do not attempt the call.
            If subagent launch is unavailable or schema-uncertain, either do the bounded work directly in the current session or classify the unit as `STALLED` with the missing runtime requirement.
            For image-based requests, first check whether the current runtime supports native image input.
            If the current model is GLM-5, or the runtime reports that it cannot read images, do not try to inspect the image directly and do not search Desktop or Downloads for screenshots.
            Require a host-provided or user-provided absolute image path and use `python .dual-agents/analyze_image.py --image-path /absolute/path/to/image.png --prompt "<bounded question>"`.
            If the current runtime truly supports native image reading, use that capability directly instead of Codex image handoff.
            If neither native image input nor an absolute image path is available, classify the unit as `STALLED` instead of improvising.
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
            Do not write ad hoc Python heredocs for spec completeness or bounded unit analysis; use the fixed analyzer and parser path only.
            If an analysis step throws a traceback or syntax error, stop immediately with `STALLED` and tell the coordinator to inspect schema, fix parser, and rerun the same bounded analysis.
            If the current model is GLM-5 or the runtime cannot read images, do not attempt direct image inspection.
            Use `python .dual-agents/analyze_image.py --image-path /absolute/path/to/image.png --prompt "<bounded question>"` only when an absolute image path is available.
            If native image input is supported in the current runtime, use that capability directly instead of Codex handoff.
            If the session is degraded by repeated malformed tool calls or timeouts, stop and point the coordinator to a stop report instead of improvising more retries.
            """
        ).strip()
        + "\n",
    }
