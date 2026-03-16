# Forum Replay Evaluation

This evaluation replays realistic dual-agent failure modes instead of only checking prompt contracts.

## Why a replay harness

Recent failures were not just bad wording. They were workflow failures with recognizable shapes:

- malformed completeness/status output leaking internal scaffolding
- post-review turns expanding into broad rewrites
- builder handoffs mixing task types
- repeated contradictions without a bounded adjudication path
- delivery-sensitive claims made without proof

The replay harness encodes those situations as deterministic scenarios and measures how much protection the workflow provides with forum mode disabled versus enabled.

## Metrics

- `scenario_protection_rate`
  - Fraction of all replay scenarios the workflow protects against.
- `critical_failure_catch_rate`
  - Fraction of critical scenarios blocked by existing controls.
- `bounded_remediation_enforcement_rate`
  - Fraction of bounded-remediation and task-bounding scenarios caught correctly.
- `adjudication_applicability_rate`
  - Fraction of adjudication-specific scenarios handled correctly.

## Results

```json
{
  "baseline": {
    "adjudication_applicability_rate": 0.333,
    "bounded_remediation_enforcement_rate": 1.0,
    "critical_failure_catch_rate": 0.8,
    "scenario_protection_rate": 0.714
  },
  "experiment": {
    "adjudication_applicability_rate": 1.0,
    "bounded_remediation_enforcement_rate": 1.0,
    "critical_failure_catch_rate": 1.0,
    "scenario_protection_rate": 1.0
  },
  "delta": {
    "adjudication_applicability_gain": 0.667,
    "bounded_remediation_gain": 0.0,
    "critical_failure_catch_gain": 0.2,
    "scenario_protection_gain": 0.286
  }
}
```

## Interpretation

- Most existing guards were already present in baseline and remain intact:
  - malformed user-facing output
  - post-review boundedness
  - task-type bounding
  - delivery proof enforcement
- The improvement is concentrated where expected:
  - repeated contradictions
  - adjudication-specific malformed outputs
- It also closes one critical gap in baseline:
  - repeated contradiction handling counted as an unprotected critical scenario in baseline and is protected in experiment

That is the right result. It means the feature is narrow and additive rather than compensating for broader workflow regressions.

## Objective assessment

The replay harness shows a real improvement, but it is limited in scope:

- Good news:
  - overall scenario protection improved from `0.714` to `1.0`
  - adjudication applicability improved from `0.333` to `1.0`
  - critical failure catch rate improved from `0.8` to `1.0`
- Constraint:
  - this does **not** prove lower network latency or eliminate `SSE read timed out`
  - it proves the workflow now has a better bounded control path when contradictions recur

## Recommendation

Adopt the feature if the goal is to improve conflict resolution discipline.

Do not oversell it as a general timeout fix. It is a workflow-control improvement, not a transport-layer cure.
