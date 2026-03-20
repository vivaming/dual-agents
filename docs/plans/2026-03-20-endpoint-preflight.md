# Endpoint Preflight Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a hard workflow gate that detects unreachable browser/URL targets before the dual-agent workflow launches broad remediation work.

**Architecture:** Extend stop classification with a dedicated `TARGET_ENDPOINT_ERROR` category, add a fixed endpoint preflight script exported into target repos, and tighten coordinator/reviewer contracts so browser and URL validation work must pass preflight before implementation continues.

**Tech Stack:** Python 3.12, Typer CLI, exported helper scripts, pytest.

---

### Task 1: Add endpoint stop classification

**Files:**
- Modify: `src/dual_agents/stop_monitor.py`
- Modify: `src/dual_agents/eval_stop_monitor.py`
- Test: `tests/test_stop_monitor.py`
- Test: `tests/test_eval_stop_monitor.py`

**Step 1:** Add `TARGET_ENDPOINT_ERROR` and detection patterns for URL/port reachability failures.

**Step 2:** Add bounded recovery guidance:
- identify target URL/port
- verify reachability
- rerun same bounded validation

**Step 3:** Add replay examples and tests.

### Task 2: Add fixed endpoint preflight helper

**Files:**
- Modify: `src/dual_agents/cli.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_export.py`

**Step 1:** Add a standalone exported script that checks URL reachability.

**Step 2:** Add a CLI entrypoint for local verification.

**Step 3:** Export the helper into `.dual-agents/endpoint_preflight.py`.

### Task 3: Tighten workflow contracts

**Files:**
- Modify: `src/dual_agents/opencode_assets.py`
- Modify: `src/dual_agents/codex_review.py`
- Test: `tests/test_opencode_assets.py`
- Test: `tests/test_codex_review.py`

**Step 1:** Require browser/URL tasks to preflight the target before broad remediation.

**Step 2:** Require immediate stop on failed preflight.

**Step 3:** Explicitly forbid launching large fix tasks when target reachability is not yet proven.

### Task 4: Verify

**Files:**
- None

**Step 1:** Run targeted pytest coverage for modified modules.

**Step 2:** Run full pytest suite.

**Step 3:** Commit isolated worktree changes.
