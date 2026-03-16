from dual_agents.eval_forum import evaluate_forum_adjudication


def test_forum_eval_shows_robustness_gain_with_bounded_growth() -> None:
    report = evaluate_forum_adjudication()

    assert report["delta"]["robustness_gain"] >= 4
    assert report["experiment"]["malformed_forum_catch_rate"] == 1.0
    assert report["delta"]["coordinator_prompt_growth_chars"] > 0
    assert report["replay"]["delta"]["scenario_protection_gain"] == 0.286
    assert report["replay"]["delta"]["adjudication_applicability_gain"] == 0.667
    assert report["replay"]["delta"]["premium_review_call_reduction"] == 0.571
    assert report["recommendation"]["adopt_forum_adjudication"] is True
