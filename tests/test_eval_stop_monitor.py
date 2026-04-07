from dual_agents.eval_stop_monitor import evaluate_stop_monitor


def test_stop_monitor_eval_classifies_known_failures() -> None:
    report = evaluate_stop_monitor()
    assert report["classification_accuracy"] >= 0.833
    assert report["scenario_count"] >= 6
