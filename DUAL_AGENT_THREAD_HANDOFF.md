# Dual Agent Thread Handoff

Use this file to start a new thread dedicated to the dual-agent workflow.

## Workspace

- Target repo: `/path/to/target-repo`
- Dual-agent repo: `/path/to/dual-agents`

## Read These First

1. `/path/to/target-repo/<workflow-control-state>.md`
2. `/path/to/dual-agents/CONSTITUTION.md`
3. `/path/to/dual-agents/dual-agent-features-master.md`
4. `/path/to/dual-agents/docs/templates/codex-decision-review-template.md`

## Thread Rules

- Treat `dual-agent-state.md` as the workflow control state.
- Do not rely on prior chat memory when the files above exist.
- Keep normal conversation on GLM.
- Use Codex only for bounded review decisions.
- If Codex review times out, split the decision and retry the smallest unresolved judgment.
- Do not start later pairs while earlier units are unresolved unless a saved review explicitly allows progression.

## Current Situation

The target repo may contain mixed artifacts from prior sessions.

Use file-backed truth, not transcript memory.

Important:
- `dual-agent-state.md` is the current control file, even if older chat summaries disagree.
- The working tree is dirty, so status must be checked from repo artifacts and git state.

## Recommended First Prompt For The New Thread

```text
This thread is only for the dual-agent workflow in /path/to/target-repo.

Read these files first and treat them as the source of truth:
- /path/to/target-repo/<workflow-control-state>.md
- /path/to/dual-agents/CONSTITUTION.md
- /path/to/dual-agents/dual-agent-features-master.md
- /path/to/dual-agents/docs/templates/codex-decision-review-template.md

Rules:
- Do not rely on prior thread memory.
- Use file-backed state.
- Keep answers concise.
- Use Codex only for bounded progression decisions.

First task:
- Summarize the current next allowed action in 5 bullets max.
- Then list any inconsistencies between dual-agent-state.md, pair review notes, and git status.
```

## If The New Thread Starts Drifting

Use this reset prompt:

```text
Stop. Re-anchor on /path/to/target-repo/<workflow-control-state>.md and saved review artifacts only.

Do not continue implementation yet.
Answer:
1. What is the current bounded unit?
2. What is its status?
3. What artifact proves it?
4. What is the next allowed action?
```
