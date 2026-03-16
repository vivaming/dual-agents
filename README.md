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
