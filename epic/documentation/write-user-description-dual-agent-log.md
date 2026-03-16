# Dual-Agent Run Log: Write User-Friendly Description

## Task
Write a user-friendly description for the dual-agents repo to help people understand:
- Basic architecture
- Purpose
- Features
- How it works

## Status: IN_PROGRESS

---

## Round 1: Initial Draft

### Delegation
- **Agent**: glm-builder
- **Scope**: Create a comprehensive, user-friendly README/description document

### Files Read for Context
- `README.md` - existing technical documentation
- `dual-agent-features-master.md` - feature tracking and architecture
- `src/dual_agents/workflow.py` - workflow stages and transitions
- `src/dual_agents/controller.py` - workflow controller and validation
- `src/dual_agents/cli.py` - CLI commands

### Key Architecture Understanding
1. **Dual-Agent Pattern**: GLM-5 (builder) + Codex CLI (reviewer)
2. **Workflow Stages**: REQUEST_RECEIVED → EPIC_DRAFT → EPIC_REVIEW → IMPLEMENTATION → SELF_REVIEW → CRITICAL_REVIEW → ADJUDICATION → DELIVERY_VERIFICATION → DEPLOY_READY
3. **Coordinator**: Local logic that orchestrates the workflow
4. **Portable Scaffold**: Can be exported to any target repo

---

## Builder Output

### Files Created
- `epic/documentation/USER_GUIDE.md` (372 lines)

### Sections Included
1. **What is Dual Agents?** - Jargon-free explanation with house-building analogy
2. **Why Use It?** - Problem/solution table addressing single-agent issues
3. **How It Works** - ASCII diagram of three roles (Builder, Reviewer, Coordinator)
4. **Workflow Overview** - Visual ASCII flowchart with all stages
5. **Key Features** - Structured review gates, loop prevention, clean output, bounded tasks
6. **Getting Started** - Step-by-step setup instructions
7. **Common Use Cases** - When to use / when not to use
8. **Tips for Success** - Practical advice

---

## Round 1: Critical Review

### Review Target
`epic/documentation/USER_GUIDE.md`

### Codex Review Result

**Verdict**: CHANGES_REQUESTED

#### Blocking Issues
1. Guide doesn't clearly explain that `/dual` is used in the *target repo* after initialization, not in this scaffold repo
2. Workflow stages are presented as documented system contract but README.md doesn't list them

**Note**: The stages ARE defined in `src/dual_agents/workflow.py` (WorkflowStage enum), so they are part of the system. However, we should clarify this is the internal workflow.

#### Non-Blocking Issues
- Clarify this is a portable scaffold early on
- Mention Codex review is limited to review gates only
- Add note about `preview`/`export` commands
- Label Forum Adjudication as experimental

---

## Round 2: Implementation Fix

### Action
Delegate to glm-builder to fix the blocking issues:
1. Clarify usage flow: install scaffold → init target repo → open target repo in OpenCode → use `/dual` there
2. Add early framing that this is a portable scaffold
3. Mention preview/export commands
4. Label Forum Adjudication as experimental

### Changes Made
- Line 5: Added callout box explaining this is a portable scaffold
- Lines 124: Added note about internal workflow state machine
- Line 208: Added note about Codex only at review gates
- Line 216: Labeled Forum Adjudication as experimental
- Lines 278-280: Added preview/export commands
- Lines 284-296: Rewrote "Using the Workflow" with clear target repo instructions

---

## Round 2: Critical Review

### Review Target
`epic/documentation/USER_GUIDE.md` (revised)

### Codex Review Result

**Verdict**: APPROVED

#### Evidence of Fixes
- Line 5: Portable scaffold framing added
- Line 208: Codex-only-at-review-gates note added
- Line 216: Forum Adjudication marked experimental
- Line 278: `preview` and `export` commands mentioned
- Lines 288, 296: `/dual` scoped to target repo, not scaffold

#### Delivery Proof Status
PROVEN

---

## Final Status: PASS

### Deliverable
- `epic/documentation/USER_GUIDE.md` (389 lines)

### Summary
Created a comprehensive, user-friendly guide for the dual-agents repo covering:
- What Dual Agents is (with house-building analogy)
- Why use it (problem/solution table)
- How it works (Builder, Reviewer, Coordinator roles)
- Workflow overview (with ASCII diagram)
- Key features (review gates, loop prevention, clean output, bounded tasks)
- Getting started (prerequisites, setup, initialization)
- Using the workflow (target repo instructions)
- Common use cases
- Tips for success

### Review Rounds
- Round 1: CHANGES_REQUESTED (5 issues identified)
- Round 2: APPROVED (all issues fixed)
