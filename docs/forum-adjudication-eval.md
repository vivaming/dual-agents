# Forum Adjudication Evaluation

This branch tests a small `FORUM_ADJUDICATION` mode for the dual-agent workflow.

## Scope

The experiment does not add a full debate engine. It adds one bounded adjudication round with:

- explicit trigger rules
- a short moderator-ruling contract
- exportable prompt text
- report validation support

## Metrics

The evaluation uses deterministic contract-level metrics rather than subjective “felt better” claims.

### Robustness metrics

- `robustness_score`: counts whether the exported coordinator and reviewer prompts contain the forum trigger and ruling contract.
- `malformed_forum_catch_rate`: percentage of malformed forum outputs rejected by the validator/controller helpers.

### Complexity and performance proxies

- `coordinator_prompt_growth_chars`
- `review_prompt_growth_chars`
- `validator_growth_chars`
- `complexity_cost_chars`

These are prompt/runtime overhead proxies. They are not wall-clock latency benchmarks, but they are useful because most recent failures came from over-broad prompt growth and long streamed turns.

## Results

Baseline means forum mode disabled. Experiment means forum mode enabled.

```json
{
  "baseline": {
    "coordinator_prompt_chars": 2654,
    "malformed_forum_catch_rate": 0.0,
    "review_prompt_chars": 2806,
    "robustness_score": 0,
    "validator_chars": 4289,
    "workflow_stage_count": 10
  },
  "delta": {
    "complexity_cost_chars": 919,
    "coordinator_prompt_growth_chars": 555,
    "malformed_forum_catch_gain": 1.0,
    "review_prompt_growth_chars": 364,
    "robustness_gain": 5,
    "validator_growth_chars": 0
  },
  "experiment": {
    "coordinator_prompt_chars": 3209,
    "malformed_forum_catch_rate": 1.0,
    "review_prompt_chars": 3170,
    "robustness_score": 5,
    "validator_chars": 4289,
    "workflow_stage_count": 10
  },
  "recommendation": {
    "adopt_forum_adjudication": true,
    "reason": "Material robustness gain with bounded prompt/validator growth."
  }
}
```

## Interpretation

- The feature materially improves bounded-conflict handling.
- It does not expand workflow stage count beyond the already-added stage.
- Prompt growth stays under 1k combined characters, which is acceptable relative to the robustness gain.
- The validator/controller path catches malformed forum outputs in all synthetic failure cases used by the harness.

## Recommendation

Keep the feature only as a narrowly-scoped adjudication mode.

Do not expand it into a general discussion forum unless a later evaluation shows a concrete benefit that outweighs the extra prompt and orchestration cost.
