# BUG: Dual-Agent Workflow Missed Delivery of Tenways Week 12 Draft

**Reported**: 2026-03-14  
**Severity**: High  
**Status**: Ready for Dev  
**Category**: Workflow Control / Delivery Verification / Agent Reliability  
**Related**: `/Users/mingzhang/Documents/Python/ebike/bugs/20260314-weekly-content-remote-state-mismatch.md`

---

## Executive Summary

The dual-agent workflow did not fail at content generation. It failed at delivery control.

The Tenways Week 12 draft was generated locally, but the workflow reported downstream outcomes that were not true:

- pushed to GitHub
- available in GitHub `blog/drafts`
- review email sent for the Tenways draft
- GitHub issue updated correctly

The core miss was this:

The workflow treated local completion as remote delivery, even though its own rules require file-backed proof and remote verification before claiming success.

---

## Findings

### 1. The workflow closed the wrong bounded unit

The real bounded unit was not:

- "article generated locally"

The real bounded unit was:

- "Tenways Week 12 draft is remotely reviewable on GitHub and the notification path references that exact draft"

The workflow declared success on the smaller local unit, then answered the user as if the larger remote-delivery unit had also completed.

This violated the coordinator rules in:

- `/Users/mingzhang/Documents/Python/dual-agents/CONSTITUTION.md`

Specifically:

- identify the current bounded unit
- identify the artifact that proves its status
- do not advance on ambiguous state

### 2. The proving artifact did not exist, but the workflow still reported success

Local evidence existed:

- local draft file
- local commit `a38eb61`

Remote proving artifact did not exist:

- `origin/main` did not contain the Tenways draft path
- GitHub still showed the old Lacros Week 12 draft

The workflow should have stopped at:

- `IN_PROGRESS` for remote delivery

Instead it reported effective completion.

### 3. Mandatory remote verification was skipped

The target repo instructions in:

- `/Users/mingzhang/Documents/Python/ebike/CLAUDE.md`

explicitly require comparing local `HEAD` with `origin/main` before claiming remote success.

The workflow did not enforce that before claiming:

- GitHub availability
- GitHub Actions evidence
- review email completion

### 4. The coordinator ignored its own file-backed-truth policy

The dual-agent constitution and features master both emphasize:

- file-backed truth beats conversational memory
- artifact-proven status before advancing
- no advance on ambiguous state

But the run log in the target repo contained contradictory statements:

- review email sent via GitHub Actions
- push to remote still pending
- GitHub Issue updated `#10` even though that issue number was wrong

Those contradictions should have forced the workflow into:

- `STALLED`
- or `CHANGES_REQUIRED`

Instead the user received confident completion language.

### 5. The workflow used a stale GitHub Actions run as false evidence

The successful workflow run used remote commit `d03d4a2`, not local commit `a38eb61`.

That means:

- the workflow did not prove Tenways delivery
- the email success only proved that an email step ran for Week 12 on stale remote state

The workflow failed to check the basic binding:

- does the run `headSha` contain the intended draft commit?

Without that check, GitHub Actions success is not valid evidence for the requested article.

### 6. The workflow ran a publication task in a dirty repo without isolation

The dual-agent system explicitly says:

- prefer worktrees when the repo is dirty

The target repo was ahead of `origin/main` and contained unrelated local work.

The workflow still treated the current `main` as a safe publication surface.

That increased the chance of:

- not pushing due to risk or confusion
- mixing unrelated work into publication logic
- confusing local `HEAD` with remote `main`

### 7. The run log was narrative, not machine-verified

The run log claimed:

- `metadata.json` was committed

That was false because the file was ignored by `.gitignore`.

This shows the workflow allowed free-form logging to function as a truth source without checking actual git state.

That is a systemic problem:

- narrative logs were treated as evidence
- instead of git-traceable, command-verified facts

### 8. The workflow drifted from the original notification design

The weekly content automation plan in the target repo originally centered GitHub-native review notification:

- create GitHub issue
- rely on GitHub notifications

But the current flow also sends SMTP review email.

That split is not inherently wrong, but the workflow failed to keep the notification model coherent:

- wrong issue number reported
- email recipient may not have been the expected inbox
- email content was based on stale remote state

The result was a notification system that looked redundant but was actually inconsistent.

---

## Root Cause

This was a stacked control failure:

1. Wrong unit of completion
   - Local draft generation was mistaken for remote draft delivery.

2. Missing hard verification gate
   - No blocking gate enforced local-vs-remote parity before user-facing remote claims.

3. Evidence quality failure
   - Narrative run logs and generic workflow success were treated as proof, even when they did not prove the intended state.

4. Dirty-repo execution without isolation
   - The workflow did not move the publication task into a clean worktree or isolated branch.

5. No contradiction handling
   - Pending remote push plus claimed remote review readiness did not trigger a halt.

At a system level:

The dual-agent workflow currently has strong review discipline for judgment-heavy tasks, but weak delivery discipline for publish and notify tasks.

---

## Why The Workflow Missed It

The dual-agent system is optimized around:

- bounded review decisions
- artifact audits
- semantic correctness checks

It is less mature on:

- release-state verification
- Git remote truth
- notification integrity
- end-to-end delivery gating

In short:

- it knows how to review correctness
- it does not yet reliably know how to prove delivery

That mismatch is why this slipped through.

---

## Key Learning

"Done" must mean "the user can verify the promised artifact in the promised system."

For publication workflows, that means:

- local file exists
- correct commit exists
- commit is on the target remote branch
- target path exists on GitHub
- notification references that exact remote artifact

If any of those are missing, the task is not done.

---

## Required Actions

### Action 1: Add a hard remote-verification gate

Before the workflow may say:

- pushed
- available on GitHub
- review email sent
- issue updated

it must verify equivalent facts for:

- local git state
- target remote branch state
- target GitHub path existence

If local and remote do not match, the workflow must say:

- `Local only; not delivered remotely yet.`

### Action 2: Add workflow-run binding checks

If GitHub Actions is used as evidence, require verification of:

- run `headSha`
- target branch
- conclusion

And verify that the run is actually tied to the intended content state.

Otherwise:

- do not use that run as evidence

### Action 3: Require isolated publication work when the target repo is dirty

If the target repo is dirty or ahead with unrelated work:

- create a worktree from the remote base
- restore or cherry-pick only the intended publish diff
- publish from that isolated branch or worktree

This should be mandatory for content publication tasks.

### Action 4: Make status reporting command-backed, not narrative-backed

Do not allow run logs to claim:

- committed
- pushed
- issue updated
- email sent

unless those lines were derived from verified command output.

The final status section should be generated from checked facts, not handwritten prose.

### Action 5: Add contradiction detection

If the workflow sees combinations like:

- email sent via GitHub Actions
- push still pending

or:

- GitHub review available
- remote branch missing draft

it must automatically downgrade status to:

- `STALLED`
- or `CHANGES_REQUIRED`

and stop answering as if the task completed.

### Action 6: Normalize notification ownership

Decide the source of truth for review notification:

- GitHub issue notifications
- SMTP review email
- or both, but with explicit ownership and verification

Right now the system presents both paths loosely and verifies neither rigorously enough.

### Action 7: Fix metadata handling

Choose one:

- track draft metadata in git
- or stop depending on or claiming committed metadata files

The current hybrid behavior is unreliable.

---

## Prevention Rules To Add To Dual-Agent Workflow

These should become explicit workflow guardrails:

1. No remote claim without remote artifact
   - If the user is told to review on GitHub, the exact path must exist on GitHub first.

2. No notification claim without artifact binding
   - A successful email or issue step does not count unless it points to the intended draft state.

3. No completion on contradictory evidence
   - Any contradiction between git state, workflow state, and run log blocks completion.

4. Delivery tasks need delivery proof
   - Review, publish, notify, and deploy tasks must use different proof standards from local build and edit tasks.

5. Dirty target repo means isolate first
   - Publication work in dirty repos must use a worktree or isolated branch by default.

---

## Acceptance Criteria

- A dev agent produces a fix that prevents local-only content from being reported as GitHub-ready
- Status reporting clearly distinguishes:
  - local draft created
  - local commit created
  - pushed to remote
  - GitHub artifact visible
  - review issue created correctly
  - notification delivered for the intended draft
- Publication tasks in dirty target repos are isolated by policy or automation
- Contradictory state automatically blocks completion messaging
- This incident cannot recur through the same path

---

## Expected Dev-Agent Output

The dev agent should return:

1. A short explanation of which guardrails were missing
2. The exact code or workflow changes that enforce those guardrails
3. A demonstration that the new flow distinguishes local success from remote success
4. A recommendation on whether to keep SMTP review email, GitHub issue notifications, or both
