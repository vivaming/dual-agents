# Dual Agent Thread Handoff

Use this file to start a new thread dedicated to the dual-agent workflow.

## Workspace

- Main repo: `/Users/mingzhang/Documents/Python/ebike`
- Dual-agent repo: `/Users/mingzhang/Documents/Python/dual-agents`

## Read These First

1. `/Users/mingzhang/Documents/Python/ebike/epic/spec-panel-gap-analysis/dual-agent-state.md`
2. `/Users/mingzhang/Documents/Python/dual-agents/CONSTITUTION.md`
3. `/Users/mingzhang/Documents/Python/dual-agents/dual-agent-features-master.md`
4. `/Users/mingzhang/Documents/Python/dual-agents/docs/templates/codex-decision-review-template.md`

## Thread Rules

- Treat `dual-agent-state.md` as the workflow control state.
- Do not rely on prior chat memory when the files above exist.
- Keep normal conversation on GLM.
- Use Codex only for bounded review decisions.
- If Codex review times out, split the decision and retry the smallest unresolved judgment.
- Do not start later pairs while earlier units are unresolved unless a saved review explicitly allows progression.

## Current Situation

The repo contains mixed artifacts from Task 12 and the workflow has made some bad sequencing decisions in prior sessions.

Use file-backed truth, not transcript memory.

Important:
- `dual-agent-state.md` is the current control file, even if older chat summaries disagree.
- The working tree is dirty, so status must be checked from repo artifacts and git state.

## Recommended First Prompt For The New Thread

```text
This thread is only for the dual-agent workflow in /Users/mingzhang/Documents/Python/ebike.

Read these files first and treat them as the source of truth:
- /Users/mingzhang/Documents/Python/ebike/epic/spec-panel-gap-analysis/dual-agent-state.md
- /Users/mingzhang/Documents/Python/dual-agents/CONSTITUTION.md
- /Users/mingzhang/Documents/Python/dual-agents/dual-agent-features-master.md
- /Users/mingzhang/Documents/Python/dual-agents/docs/templates/codex-decision-review-template.md

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
Stop. Re-anchor on /Users/mingzhang/Documents/Python/ebike/epic/spec-panel-gap-analysis/dual-agent-state.md and saved review artifacts only.

Do not continue implementation yet.
Answer:
1. What is the current bounded unit?
2. What is its status?
3. What artifact proves it?
4. What is the next allowed action?
```
