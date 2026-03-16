from dual_agents.eval_replay import evaluate_replay_scenarios


def test_replay_eval_improves_adjudication_without_regressing_core_guards() -> None:
    report = evaluate_replay_scenarios()

    assert report["baseline"]["critical_failure_catch_rate"] == 0.8
    assert report["experiment"]["critical_failure_catch_rate"] == 1.0
    assert report["baseline"]["bounded_remediation_enforcement_rate"] == 1.0
    assert report["experiment"]["bounded_remediation_enforcement_rate"] == 1.0
    assert report["delta"]["adjudication_applicability_gain"] == 0.667
    assert report["delta"]["critical_failure_catch_gain"] == 0.2
    assert report["delta"]["scenario_protection_gain"] == 0.286
    assert report["baseline"]["premium_review_calls_per_scenario"] == 1.0
    assert report["experiment"]["premium_review_calls_per_scenario"] == 0.429
    assert report["delta"]["premium_review_call_reduction"] == 0.571
    assert report["delta"]["estimated_premium_char_reduction"] == 3350
