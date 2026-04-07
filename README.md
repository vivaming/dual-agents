# Dual Agents

Dual Agents is a portable Python scaffold for a dual-agent workflow built around two tools:

- `OpenCode` runs the implementation agent with `GLM-5`
- `Codex CLI` runs the critical review step with your ChatGPT-authenticated Codex session

The coordinator logic stays local so the workflow can be reused across projects without copying per-repo model wiring.

## Current Design

- `glm-builder` is generated as an OpenCode agent using the Z.AI coding endpoint
- `dual-coordinator` is generated as an OpenCode agent and `/dual` command contract
- `codex-reviewer` is represented as a local Codex review prompt and command template
- workflow state transitions are encoded in Python
- a lightweight runtime controller validates reviewer output and blocks invalid delivery completion
- review packets are narrowed into small decision-shaped requests before Codex review
- clean user-facing output is enforced by default so internal reasoning and tool transcript fragments do not leak into answers
- coverage/completeness/status requests default to structured per-brand or per-item summaries instead of analysis scaffolding
- an experimental `FORUM_ADJUDICATION` mode can resolve repeated contradictions with one bounded moderator ruling instead of open-ended debate

## Required Local Setup

1. Make sure `opencode` is installed and available on your shell `PATH`
2. Make sure `codex` is installed and logged in with `codex --login`
3. Set your GLM key in the environment

```bash
export GLM_API_KEY=your_key_here
```

## Quickstart

```bash
git clone <your-fork-or-this-repo>
cd dual-agents
python -m venv .venv
source .venv/bin/activate
pip install -e .
export GLM_API_KEY=your_key_here
dual-agents doctor
dual-agents init-target --output-dir /path/to/target-repo
```

After initialization, open the target repo and commit the generated `.opencode/` and `.dual-agents/` assets there.

## Usage

Preview generated assets:

```bash
uv run python -m dual_agents.cli preview
```

Export OpenCode and Codex assets into a target repository:

```bash
uv run python -m dual_agents.cli export --output-dir /path/to/project
```

Check whether a new environment is ready:

```bash
dual-agents doctor
```

Initialize a target repo with the latest workflow assets and printed next steps:

```bash
dual-agents init-target --output-dir /path/to/project
```

This writes:

- `.opencode/opencode.json`
- `.opencode/agents/*.md`
- `.opencode/commands/dual.md`
- `.dual-agents/codex-review.txt`
- `.dual-agents/validate_report.py`
- `.dual-agents/validate_review.py`
- `.dual-agents/run-state.json` once a bounded unit is started through the CLI

The generated workflow now requires saved review artifacts under `.dual-agents/reviews/<unit-slug>/`:

- `final-review.txt` for the critical review before any `PASS` or completion claim

Validate those files with `.dual-agents/validate_review.py` before allowing progression or completion.
The default workflow starts each bounded unit with implementation, not a mandatory pre-implementation review. Use a design review before implementation only when the user explicitly asks for one.
After one bounded unit passes final review, the next bounded unit may begin implementation normally.
If a critical review returns blocking issues, those findings remain mandatory remediation work for the current bounded unit until a later review clears them or the 5-round loop budget for that issue cluster is exhausted. If the loop still has blockers after 5 rounds, pause and wait for user instruction.
Review gates are file-backed: the workflow should accept only the expected saved artifact for the current bounded unit, not copied review text or remembered conclusions.
When integrating the controller directly, start each bounded unit with `begin_new_bounded_unit(<unit-slug>)`, run implementation, then consume final reviews through `submit_saved_review()`.
When using the CLI orchestration path, use `dual-agents start-unit` to create/update `.dual-agents/run-state.json`. By default it starts in implementation mode; pass `--start-mode review` for an explicit pre-implementation gate, or rely on `--start-mode auto` with `--task-summary "..."` and optionally `--task-file /path/to/task.md` to infer review mode from the user's statement plus the task file. In auto mode the classifier prefers implementation when the epic/task looks delivery-shaped, for example with concrete file modifications, required changes, acceptance criteria, and verification steps. It switches to pre-implementation review when the statement or task text looks like planning, proposal, architecture, or explicit design review work. The CLI also tries a best-effort `epic/**/*.md` match from the unit slug. Then use `dual-agents review-gate` to run Codex and persist the review artifact plus updated bounded-unit state.
If you already have a saved review artifact and do not want to run Codex again, use `dual-agents submit-review-artifact --unit-slug <unit> --mode <lead|final> --review-file <path> --repo-root <repo>` to validate and advance workflow state from that existing file, but only when that file was previously produced by Codex CLI. Do not use it for a coordinator-authored or manually improvised review.

For the forum-adjudication experiment and its evaluation metrics, see `docs/forum-adjudication-eval.md` and `docs/forum-replay-eval.md`.
For the premium-review cost optimization experiment, see `docs/premium-token-eval.md`.

## Contribution Model

- Contributions should be submitted by pull request.
- Nothing should be merged directly without maintainer review and approval.
- If you build on this project in a redistribution, preserve the license and `NOTICE` file.
- See `CONTRIBUTING.md` for the expected PR flow.

## License

This project uses the Apache License 2.0. See `LICENSE` and `NOTICE`.

## Secrets

The current scaffold requires:

- `GLM_API_KEY`

No `OPENAI_API_KEY` is required for the review path when Codex CLI is used as the reviewer runtime.
