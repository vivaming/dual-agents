# Stop Monitoring Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture and classify dual-agent workflow stop/failure signals so repeated pauses can be diagnosed with evidence instead of anecdotal transcript reading.

**Architecture:** Add a small stop-monitor module that classifies transcript snippets into concrete stop categories, export a portable monitor script into target repos, and teach the coordinator to emit a bounded stop report when the workflow stalls. Back it with deterministic replay-style tests built from real failure patterns.

**Tech Stack:** Python 3.12, Typer-exported helper scripts, regex-based transcript classification, pytest

---

### Task 1: Add stop-monitor domain model

**Files:**
- Create: `src/dual_agents/stop_monitor.py`
- Test: `tests/test_stop_monitor.py`

- [ ] Define stop categories and the `StopSignal` dataclass.
- [ ] Implement transcript classification for timeout, tool-schema, malformed-output, data-shape, and capability mismatch failures.
- [ ] Add deterministic tests for the known transcript patterns.

### Task 2: Export a portable monitoring script

**Files:**
- Modify: `src/dual_agents/cli.py`
- Modify: `tests/test_export.py`

- [ ] Add a script builder that exports `.dual-agents/monitor_stop.py`.
- [ ] Ensure `export` writes the new script into target repos.
- [ ] Extend export tests to verify the file exists.

### Task 3: Teach prompts to emit bounded stop reports

**Files:**
- Modify: `src/dual_agents/opencode_assets.py`
- Modify: `src/dual_agents/codex_review.py`
- Modify: `tests/test_opencode_assets.py`
- Modify: `tests/test_codex_review.py`

- [ ] Add coordinator instructions for a bounded stop report after pauses/stalls.
- [ ] Add reviewer instructions to reject sessions that keep retrying after a classified stop.
- [ ] Verify exported prompts mention stop classification and fresh-session recovery.

### Task 4: Add replay evaluation for stop monitoring

**Files:**
- Create: `src/dual_agents/eval_stop_monitor.py`
- Test: `tests/test_eval_stop_monitor.py`

- [ ] Build a small scenario set from observed pauses.
- [ ] Measure stop-classification coverage and recommendation quality.
- [ ] Expose a simple JSON report for future regression checks.

### Task 5: Verify and ship

**Files:**
- Modify: `README.md` (if needed)

- [ ] Run targeted tests for stop monitoring.
- [ ] Run the full pytest suite.
- [ ] Commit only the stop-monitoring changes from the isolated worktree.
