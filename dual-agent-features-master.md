# Dual Agent Features Master

## Maintenance Protocol - CRITICAL RULES

### features-master.md Maintenance Protocol
**Purpose**: EFFICIENT LOOKUP REFERENCE for LLM to understand current infrastructure
**Format**: Concise function documentation, NOT verbose changelog
- Update existing entries with new capabilities
- Add new file references when needed
- Remove outdated/deprecated sections
- Format: `- **functionName**: Description - Scope - Category`
- NEVER add daily updates or implementation narratives

⚠️ **ALWAYS READ THESE RULES BEFORE MAKING ANY UPDATES** ⚠️
- These rules must never be removed or modified
- This section must always remain at the top of the file
- All updates must strictly follow this protocol

This file tracks the current capabilities, constraints, and proven behaviors of the dual-agent system.

## Active Architecture

- **dual-coordinator**: Primary OpenCode conversation agent using `zai/glm-5`
- **glm-builder**: OpenCode implementation agent using `zai/glm-5`
- **independent-auditor**: GLM-based checkpoint agent for stuck loops
- **codex reviewer**: Local `codex` CLI used for critical review gates

## Global OpenCode Setup

- **default model**: `zai/glm-5`
- **default agent**: `dual-coordinator`
- **provider**: Z.AI via OpenAI-compatible endpoint
- **base URL**: `https://api.z.ai/api/coding/paas/v4/`
- **env key**: `GLM_API_KEY`

## Supported Workflow Patterns

- **normal conversation**: stay on `dual-coordinator`
- **implementation delegation**: coordinator routes work to `glm-builder`
- **loop checkpointing**: coordinator invokes `independent-auditor` after repeated failed loops
- **explicit dual workflow trigger**: `/dual ...`
- **phrase trigger**: `sort it out with dual agent workflow`
- **critical review escalation**: use local Codex CLI only at review gates
- **complex team mode**: coordinator can split complex work into bounded parallel tracks and reassemble them

## Agent Skill Strategy

- **dual-coordinator**: planning, orchestration, worktree, and governance skills
- **glm-builder**: task-specific domain skills chosen by work type
- **independent-auditor**: minimal context plus the most relevant goal, findings, and evidence
- **codex reviewer**: review only; pass minimal repo context rather than full skill sprawl

## Review Policy

- **ordinary chat**: do not invoke Codex
- **critical review**: invoke Codex when:
  - user explicitly asks for GPT / Codex review
  - workflow reaches a formal review gate
  - independent judgment is needed on blocking issues
- **mandatory progression review**: invoke Codex before accepting blocker claims, exception-based closure, or progression past previously partial work - Flow control - Coordinator
- **bounded decision review**: Codex review should cover one judgment at a time, not a mixed bundle of code, docs, status, and release decisions - Token economy - Coordinator
- **timeout narrowing rule**: if a Codex review times out, split the packet and retry the smallest unresolved judgment instead of rerunning the same broad review - Review resilience - Coordinator
- **review default**: Codex reviews first; edits are not the default path

## Feedback Loop Policy

- **default loop budget**: 5 review/fix rounds per issue cluster
- **first exhaustion**: invoke `independent-auditor`
- **auditor continue verdict**: reset loop budget once
- **second exhaustion**: pause and report findings to the user
- **goal**: avoid overkill, token burn, and direction drift

## Repo Interaction Rules

- **run from project root**: preferred
- **dirty repo handling**: use worktrees when necessary
- **local instruction priority**: repo-local instructions and skills override generic assumptions
- **high-risk direction changes**: ask user first before changing direction, creating epics, or removing files

## Persisted Assets

- **global config**: `$HOME/.config/opencode/opencode.json`
- **global coordinator agent**: `$HOME/.config/opencode/agents/dual-coordinator.md`
- **global builder agent**: `$HOME/.config/opencode/agents/glm-builder.md`
- **global dual command**: `$HOME/.config/opencode/commands/dual.md`
- **Codex decision review template**: `docs/templates/codex-decision-review-template.md`

## Proven Integrations

- **OpenCode + Z.AI**: validated with `glm-builder`
- **Codex CLI review path**: validated independently
- **target-repo workflow context**: validated in a real downstream project

## Current Constraints

- **terminal compaction risk**: session context may disappear from visible terminal history
- **durable logging not automatic yet**: must be requested or implemented
- **Codex is scarce**: should remain review-only unless explicitly overridden
- **GLM key currently stored in shell profile**: convenient but not ideal for long-term secret hygiene

## Run Log Convention

For meaningful multi-round runs, create persistent repo logs instead of relying on terminal history.

Recommended pattern:

- `epic/<epic-name>/<task>-dual-agent-log.md`
- `epic/<epic-name>/<task>-codex-review-round1.md`
- `epic/<epic-name>/<task>-codex-review-round2.md`

Example:

- `epic/spec-panel-gap-analysis/task12-pair2-dual-agent-log.md`

Rule:

- bootstrap the run log before substantial complex work begins
- append each round with findings, files changed, tests run, and remaining blockers

## Anti-Ramble Protocol

- **narrow-answer mode**: Simple status questions must be answered directly, with `Yes.` or `No.` first when appropriate - Response discipline - Coordinator
- **file-first evidence**: Status answers should prefer saved review files, run logs, review notes, and git state over transcript reconstruction - Reliability - Coordinator
- **short-status format**: Simple status answers should stay within 1 short paragraph or 5 short bullets - Response discipline - Coordinator
- **no scratch output**: Do not dump raw scratchpad, malformed shell snippets, todos, or partial summaries into user-facing status answers - Output hygiene - Coordinator
- **pair-boundary reset**: Treat each pair or bounded unit as a fresh checkpoint and avoid open-ended multi-pair runs unless explicitly requested - Scope control - Coordinator
- **artifact re-anchor**: If the session becomes noisy, repetitive, or stops producing artifacts, pause and re-anchor on saved files before continuing - Recovery - Coordinator
- **narrow Codex review**: If Codex review appears stalled, rerun with a smaller review target instead of keeping one broad review prompt open - Review resilience - Coordinator

## Coordinator Decision Guardrails

- **bound-current-unit**: Always identify the current bounded unit of work before taking action - Sequencing - Coordinator
- **allowed-states-only**: Use only `NOT_STARTED`, `IN_PROGRESS`, `PASS`, `PASS_WITH_EXCEPTION`, `CHANGES_REQUIRED`, `BLOCKED`, `STALLED` as unit states - State control - Coordinator
- **no-advance-on-ambiguous-state**: Treat `PARTIAL`, `UNCLEAR`, or `MIXED` as unresolved until converted to an allowed state - Sequencing - Coordinator
- **artifact-proven-status**: Before advancing, identify the saved artifact that proves current status - Evidence discipline - Coordinator
- **advance-only-on-closure**: Only `PASS` and `PASS_WITH_EXCEPTION` allow the next bounded unit to start - Flow control - Coordinator
- **explicit-exception-record**: `PASS_WITH_EXCEPTION` requires a written exception record with reason, evidence, impact, and why progression is allowed - Exception handling - Coordinator
- **unfinished-work-first**: Interpret "finish the rest" as "finish all unfinished work in correct sequence", not "jump to later numbered units" - Sequencing - Coordinator
- **single-next-action**: When a unit is unresolved, choose exactly one next action: remediate, review/audit, or pause for guidance - Decision discipline - Coordinator
- **file-backed-truth**: Prefer run logs, review files, review notes, and git state over transcript memory when deciding what to do next - Reliability - Coordinator
- **fresh-boundary-reset**: After each bounded unit, summarize to files and prefer a fresh subagent or session context for the next unit - Context control - Coordinator
- **challenge-blocker-premise**: Before accepting `BLOCKED` or external-exception conclusions, verify current targets, pipeline support, and conflicting repo evidence - Review discipline - Coordinator
- **external-vs-internal-check**: Distinguish true external blockers from stale targets, missing parser support, or other internal gaps before allowing progression - Root-cause control - Coordinator
- **review-allows-progression**: When progression is in doubt, require Codex to explicitly answer whether the next bounded unit may start - Flow control - Coordinator

## Recent Key Learnings

- **review gates add real value**: Codex surfaced semantic issues missed by the implementation pass
- **semantic correctness matters more than coverage metrics**: high coverage can still hide wrong canonicalization
- **pair-by-pair rollout is the right discipline**: Task 12 should expand only after each pair clears blocking review
- **repo-local context is essential**: running the workflow from the project directory materially improves coordination quality
- **loop budgets are necessary**: repeated fix/review cycles need a hard cap and an independent direction check
