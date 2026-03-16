# Codex Decision Review Template

Use this template when the coordinator needs a progression decision from Codex / GPT.

## Purpose

Keep review packets:

- evidence-first
- conclusion-light
- one decision at a time
- small enough to avoid timeout and token waste

## Rules

- review one brand or one bounded decision at a time
- do not bundle multiple unrelated judgments into one packet
- do not preload the packet with final classifications like `TRUE EXTERNAL BLOCKER`
- do not include long implementation proposals unless the reviewer asked for them
- point Codex to primary repo artifacts first, not a long derived narrative
- if a prior review timed out, reduce scope further before retrying
- prefer saving the packet to a file and asking Codex to review that file plus a few primary artifacts
- avoid shell pipelines that truncate or mangle the review output

## Packet Structure

```md
# Review Request: <short decision name>

## Decision Needed
- <one sentence>

## Evidence Files
- <path 1>
- <path 2>
- <path 3>

## Facts Observed
- <fact 1>
- <fact 2>
- <fact 3>

## Open Questions
1. <question 1>
2. <question 2>
3. <question 3>

## Required Output Format
- Verdict: PASS | PASS_WITH_EXCEPTION | CHANGES_REQUIRED | BLOCKED
- Cause: INTERNAL | EXTERNAL | MIXED
- Blocking issues:
- Evidence relied on:
- Can next bounded unit start: YES | NO
- Required next action:
```

## Timeout Recovery

If the first review times out:

1. split the decision into smaller packets
2. remove implementation proposals and broad summaries
3. keep only the minimum evidence files needed
4. ask Codex only for the unresolved judgment
5. save the result to a repo file before continuing

## Juiced Example

```md
# Review Request: Juiced Classification

## Decision Needed
- Determine whether Juiced is truly blocked externally or still requires internal target/pipeline remediation.

## Evidence Files
- data/juiced/BLOCKED.md
- data/juiced/ground_truth/field_inventory.md
- scripts/capture_ground_truth.py
- scripts/extract_from_ground_truth.py
- scripts/brand_configs/juiced.json

## Facts Observed
- capture_ground_truth.py contains Juiced targets
- extract_from_ground_truth.py does not currently contain Juiced in BRAND_PRODUCTS
- blocker note was based on tested URLs that may be stale
- brand config and planning docs suggest current Shopify-backed Juiced models exist

## Open Questions
1. Is this a true external blocker?
2. Or is it stale targets and missing pipeline support?
3. Can the workflow advance past Pair 3: YES or NO?

## Required Output Format
- Verdict: PASS | PASS_WITH_EXCEPTION | CHANGES_REQUIRED | BLOCKED
- Cause: INTERNAL | EXTERNAL | MIXED
- Blocking issues:
- Evidence relied on:
- Can next bounded unit start: YES | NO
- Required next action:
```

## Super73 Example

```md
# Review Request: Super73 Target Normalization

## Decision Needed
- Determine whether Pair 4 can be closed or whether canonical Super73 targets must be normalized first.

## Evidence Files
- epic/spec-panel-gap-analysis/pair4-review-note.md
- data/super73/PARTIAL.md
- scripts/capture_ground_truth.py
- scripts/extract_from_ground_truth.py
- scripts/brand_configs/super73.json
- epic/spec-panel-gap-analysis/phase0_audit.md

## Facts Observed
- target lists differ across planning and script files
- RX target redirects to a collection page
- other Super73 products appear valid
- parser support for Super73 exists in extract_from_ground_truth.py

## Open Questions
1. Is Pair 4 still CHANGES_REQUIRED?
2. What is the canonical Super73 target set?
3. Can the workflow advance past Pair 4: YES or NO?

## Required Output Format
- Verdict: PASS | PASS_WITH_EXCEPTION | CHANGES_REQUIRED | BLOCKED
- Cause: INTERNAL | EXTERNAL | MIXED
- Blocking issues:
- Evidence relied on:
- Can next bounded unit start: YES | NO
- Required next action:
```
