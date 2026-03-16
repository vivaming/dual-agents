# Premium Token Optimization Evaluation

This experiment measures whether a narrow GPT escalation policy can reduce premium-model usage without weakening workflow protections.

## Optimization

The optimized policy keeps GPT review only for:

- repeated review loops
- contradictory evidence
- delivery-sensitive work
- high-risk actions
- structural task changes

Ordinary, low-risk, well-bounded units are assumed to stay on GLM plus local validators.

## Metrics

- `premium_review_calls_per_scenario`
- `estimated_premium_chars`
- `critical_failure_catch_rate`
- `scenario_protection_rate`
- `bounded_remediation_enforcement_rate`
- `adjudication_applicability_rate`

## Results

```json
{
  "baseline": {
    "premium_review_calls_per_scenario": 1.0,
    "estimated_premium_chars": 6550,
    "critical_failure_catch_rate": 0.8,
    "scenario_protection_rate": 0.714
  },
  "experiment": {
    "premium_review_calls_per_scenario": 0.429,
    "estimated_premium_chars": 3200,
    "critical_failure_catch_rate": 1.0,
    "scenario_protection_rate": 1.0
  },
  "delta": {
    "premium_review_call_reduction": 0.571,
    "estimated_premium_char_reduction": 3350,
    "critical_failure_catch_gain": 0.2,
    "scenario_protection_gain": 0.286
  }
}
```

## Interpretation

- Premium review frequency drops by about `57.1%`.
- Estimated premium review payload drops by about `51.1%` (`3350 / 6550`).
- Critical replay protection does not regress. It improves in this scenario set because repeated contradictions now escalate correctly.

## Objective conclusion

This optimization is worth considering only because the saved premium usage does not come with weaker replay protection.

If future real-world telemetry shows that ordinary GLM review misses high-risk issues, the escalation policy should be tightened again.
