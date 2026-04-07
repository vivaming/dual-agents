# Dual Agent Watchdog and Run-State Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable bounded-unit state model and an automatic watchdog so the dual-agent workflow cannot sit idle for long periods without either producing artifacts or explicitly transitioning to `STALLED`.

**Architecture:** The workflow should treat persisted run-state as the control plane, review artifacts as the evidence plane, and CLI/orchestration commands as thin executors. A watchdog command should read run-state plus artifact timestamps, classify inactivity, and force a durable stop transition when the current unit is not making artifact-backed progress.

**Tech Stack:** Python 3.12, Typer, Pydantic, pytest, JSON file persistence, filesystem mtime checks

---

## File Structure

**New files**
- `src/dual_agents/watchdog.py`
- `tests/test_watchdog.py`

**Modified files**
- `src/dual_agents/state.py`
- `src/dual_agents/controller.py`
- `src/dual_agents/cli.py`
- `src/dual_agents/opencode_assets.py`
- `README.md`
- `CONSTITUTION.md`
- `epic/documentation/USER_GUIDE.md`

**Responsibilities**
- `src/dual_agents/state.py`
  Stores durable run-state schema, bounded-unit metadata, timestamps, open issue cluster metadata, and stop-state fields.
- `src/dual_agents/watchdog.py`
  Computes inactivity, missing-artifact conditions, overdue phases, and the resulting stop/escalation decision.
- `src/dual_agents/controller.py`
  Remains the policy engine for allowed state transitions; watchdog output must flow through controller-compatible states instead of inventing parallel workflow logic.
- `src/dual_agents/cli.py`
  Exposes exact operational commands for `start-unit`, `review-gate`, `heartbeat`, `watchdog-check`, and `stop-unit`.
- `src/dual_agents/opencode_assets.py`
  Teaches target repos to use the watchdog commands and the persisted run-state path.
- Docs
  Explain the operational model, thresholds, and recovery path.

---

## Target Design

### Persisted State Schema

The durable state file remains:

- `.dual-agents/run-state.json`

The top-level schema should become:

```json
{
  "current_unit": {
    "unit_slug": "task-05-supporting-pages",
    "stage": "implementation",
    "started_at": "2026-03-28T09:00:00Z",
    "updated_at": "2026-03-28T09:07:00Z",
    "last_progress_at": "2026-03-28T09:07:00Z",
    "last_heartbeat_at": "2026-03-28T09:08:30Z",
    "review_fix_rounds_used": 1,
    "lead_review_required": false,
    "critical_review_required": false,
    "current_builder_task": "Create second supporting page",
    "current_builder_task_type": "CONTENT_EDIT",
    "expected_lead_review_path": ".dual-agents/reviews/task-05-supporting-pages/lead-review.txt",
    "expected_final_review_path": ".dual-agents/reviews/task-05-supporting-pages/final-review.txt",
    "required_next_artifacts": [
      "builder_result",
      "final_review_request",
      "final_review_artifact"
    ],
    "open_blocking_issues": [],
    "last_stop_reason": null,
    "idle_timeout_seconds": 300,
    "hard_stop_timeout_seconds": 600
  }
}
```

Required schema rules:

- `started_at`, `updated_at`, `last_progress_at`, and `last_heartbeat_at` must be RFC 3339 timestamps.
- `required_next_artifacts` must be explicit and stage-dependent; silence is never inferred as acceptable.
- `open_blocking_issues` must persist the currently active remediation cluster after a `CHANGES_REQUESTED` review.
- `last_stop_reason` must be set when the watchdog forces the unit into `STALLED`.
- Timeout thresholds must live in state so target repos can inspect the exact values used for the current run.

### Valid Long-Lived States

The bounded unit may remain in only these long-lived states:

- `EPIC_REVIEW`
- `IMPLEMENTATION`
- `CRITICAL_REVIEW`
- `ADJUDICATION`
- `FORUM_ADJUDICATION`
- `STALLED`
- `DEPLOY_READY`

`Thinking` is not a valid durable state.

### Progress Definition

A bounded unit counts as making progress only when at least one of the following happens:

- `run-state.json` is updated with a new stage or a new required-next-artifact set
- a review artifact is created or modified
- a builder result is recorded
- the active remediation issue cluster changes
- the coordinator explicitly records a stop transition

Plain transcript chatter, “Thinking:” output, or repeated restatements of intent are not progress.

---

## Timeout Policy

Use two thresholds, not one:

- **Soft idle timeout:** `300` seconds (`5` minutes)
- **Hard stop timeout:** `600` seconds (`10` minutes)

Reasoning:

- The repo constitution says an apparently stalled step should only wait briefly before rerun or pause.
- Review gates are artifact-producing steps and should fail fast.
- Implementation cycles can take longer overall, but they should not remain artifact-silent for 10+ minutes.

Per-stage rules:

- `EPIC_REVIEW`
  - Soft timeout: 180 seconds
  - Hard timeout: 420 seconds
- `IMPLEMENTATION`
  - Soft timeout: 300 seconds
  - Hard timeout: 600 seconds
- `CRITICAL_REVIEW`
  - Soft timeout: 180 seconds
  - Hard timeout: 420 seconds
- `REMEDIATION` (implemented as `IMPLEMENTATION` + open blocking issues)
  - Soft timeout: 300 seconds
  - Hard timeout: 600 seconds
- `FORUM_ADJUDICATION`
  - Soft timeout: 180 seconds
  - Hard timeout: 420 seconds

Timeout behavior:

- Soft timeout:
  - write a warning to state
  - emit a stop-classification candidate
  - require either heartbeat or artifact progress before continuing
- Hard timeout:
  - force state to `STALLED`
  - save stop reason and evidence
  - require explicit bounded recovery step before resuming

---

## Watchdog Rules

### Rule 1: Artifact Silence

If the current stage expects an artifact and neither the artifact nor `last_progress_at` changes before soft timeout:

- classify as `SESSION_DEGRADATION`
- warn in run-state

If that continues to hard timeout:

- transition to `STALLED`

### Rule 2: Missing Required Gate Artifact

If the stage is `EPIC_REVIEW` or `CRITICAL_REVIEW` and the expected review file does not exist by hard timeout:

- transition to `STALLED`
- next action: rerun the same bounded review gate

### Rule 3: Review Result With Open Blocking Issues

If a final review returns `CHANGES_REQUESTED`:

- persist blocking issues in `open_blocking_issues`
- require the next state to remain on the same bounded unit
- watchdog must reject later-task progression while `open_blocking_issues` is non-empty

### Rule 4: Repeated Idle Stall

If the same `unit_slug` reaches `STALLED` twice for inactivity without a new review artifact or changed issue cluster:

- require escalation path
- next action must be one of:
  - `FORUM_ADJUDICATION`
  - independent audit
  - user-guided pause

### Rule 5: Heartbeat Is Not Progress

A heartbeat can extend soft timeout once, but not indefinitely.

- Heartbeat updates `last_heartbeat_at`
- Heartbeat does not update `last_progress_at`
- More than one consecutive heartbeat window without new artifacts should still hard-stop the unit

---

## Exact CLI Commands

### Command 1: Start bounded unit

```bash
dual-agents start-unit \
  --unit-slug task-05-supporting-pages \
  --repo-root /path/to/repo
```

Expected result:

- creates or updates `.dual-agents/run-state.json`
- sets stage to `epic_review`
- writes expected lead/final review paths

### Command 2: Run lead/final review gate

```bash
dual-agents review-gate \
  --unit-slug task-05-supporting-pages \
  --mode lead \
  --request-file /path/to/review-request.md \
  --repo-root /path/to/repo
```

Expected result:

- runs `codex`
- writes review artifact
- validates the artifact
- updates `run-state.json`

### Command 3: Record bounded heartbeat

```bash
dual-agents heartbeat \
  --unit-slug task-05-supporting-pages \
  --repo-root /path/to/repo \
  --note "Waiting on bounded builder handoff result"
```

Expected result:

- updates `last_heartbeat_at`
- appends short note to state or stop-history
- does not count as progress

### Command 4: Run watchdog check

```bash
dual-agents watchdog-check \
  --repo-root /path/to/repo
```

Expected result:

- inspects `run-state.json`
- checks expected artifact timestamps
- returns one of:
  - `OK`
  - `WARN`
  - `STALLED`
- if `STALLED`, updates run-state and writes stop reason

### Command 5: Force bounded stop

```bash
dual-agents stop-unit \
  --repo-root /path/to/repo \
  --reason "No artifact progress within hard timeout"
```

Expected result:

- sets stage to `stalled`
- records explicit stop reason
- requires bounded recovery before resume

### Command 6: Resume same bounded unit

```bash
dual-agents start-unit \
  --unit-slug task-05-supporting-pages \
  --repo-root /path/to/repo
```

Resume rule:

- allowed only if current state is `STALLED` or the unit is brand new
- must preserve prior `review_fix_rounds_used`
- must not clear `open_blocking_issues` unless a new review artifact clears them

---

## Implementation Tasks

### Task 1: Extend persisted state schema

**Files:**
- Modify: `src/dual_agents/state.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Add timestamp and watchdog fields**

Add:

- `started_at`
- `updated_at`
- `last_progress_at`
- `last_heartbeat_at`
- `required_next_artifacts`
- `open_blocking_issues`
- `last_stop_reason`
- `idle_timeout_seconds`
- `hard_stop_timeout_seconds`

- [ ] **Step 2: Add state mutation helpers**

Add helpers such as:

- `mark_progress()`
- `mark_heartbeat()`
- `mark_stalled()`
- `set_required_next_artifacts()`

- [ ] **Step 3: Run focused tests**

Run: `pytest tests/test_state.py -q`
Expected: PASS

### Task 2: Add watchdog engine

**Files:**
- Create: `src/dual_agents/watchdog.py`
- Test: `tests/test_watchdog.py`

- [ ] **Step 1: Write watchdog decision model**

Add typed outputs such as:

- `WatchdogStatus.OK`
- `WatchdogStatus.WARN`
- `WatchdogStatus.STALLED`

- [ ] **Step 2: Implement inactivity checks**

Implement:

- missing expected artifact detection
- soft timeout warning
- hard timeout stop
- repeated idle-stall escalation

- [ ] **Step 3: Run focused tests**

Run: `pytest tests/test_watchdog.py -q`
Expected: PASS

### Task 3: Wire watchdog into CLI

**Files:**
- Modify: `src/dual_agents/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Add `heartbeat` command**

Behavior:

- requires current unit in run-state
- updates heartbeat timestamp
- returns JSON summary

- [ ] **Step 2: Add `watchdog-check` command**

Behavior:

- loads state
- runs watchdog
- persists warning or stalled state
- returns JSON summary

- [ ] **Step 3: Add `stop-unit` command**

Behavior:

- explicit stop transition
- saves stop reason to run-state

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_cli.py -q`
Expected: PASS

### Task 4: Integrate controller-compatible transitions

**Files:**
- Modify: `src/dual_agents/controller.py`
- Test: `tests/test_controller.py`

- [ ] **Step 1: Ensure stop transitions are legal**

The watchdog must not invent parallel state semantics.

- `STALLED` must remain a controller-recognized unit status
- resume rules must be explicit

- [ ] **Step 2: Preserve remediation cluster state**

When `CHANGES_REQUESTED` occurs:

- save blocking issue cluster
- prevent later-task start while cluster remains open

- [ ] **Step 3: Run focused tests**

Run: `pytest tests/test_controller.py -q`
Expected: PASS

### Task 5: Refresh generated workflow assets and docs

**Files:**
- Modify: `src/dual_agents/opencode_assets.py`
- Modify: `README.md`
- Modify: `CONSTITUTION.md`
- Modify: `epic/documentation/USER_GUIDE.md`
- Test: `tests/test_opencode_assets.py`

- [ ] **Step 1: Add watchdog commands to generated instructions**

Target repos must be told:

- start the unit
- run the gate
- heartbeat if needed
- watchdog-check on idle
- stop on hard timeout

- [ ] **Step 2: Document timeout policy**

Document exact thresholds and the meaning of soft vs hard timeout.

- [ ] **Step 3: Run focused tests**

Run: `pytest tests/test_opencode_assets.py -q`
Expected: PASS

### Task 6: Run end-to-end verification

**Files:**
- Test: `tests/test_state.py`
- Test: `tests/test_watchdog.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_controller.py`
- Test: `tests/test_opencode_assets.py`

- [ ] **Step 1: Run targeted suite**

Run:

```bash
pytest tests/test_state.py tests/test_watchdog.py tests/test_cli.py tests/test_controller.py tests/test_opencode_assets.py -q
```

Expected: PASS

- [ ] **Step 2: Run broader regression suite**

Run:

```bash
pytest -q
```

Expected: PASS, or only pre-existing unrelated failures

---

## Acceptance Criteria

- The workflow cannot remain artifact-silent past the hard timeout without becoming `STALLED`.
- The current bounded unit is always recoverable from `.dual-agents/run-state.json`.
- Review gates still require saved review artifacts and now also update durable run-state.
- `heartbeat` exists but cannot mask true lack of progress indefinitely.
- `watchdog-check` provides a deterministic recovery path instead of prolonged idle waiting.
- Repeated idle stalls on the same unit escalate rather than looping forever.

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-03-28-dual-agent-watchdog-run-state.md`. Ready to execute?
