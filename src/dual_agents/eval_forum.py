from __future__ import annotations

import json
from dataclasses import dataclass

from dual_agents.cli import build_report_validator_script, default_workflow_config
from dual_agents.codex_review import build_review_prompt
from dual_agents.eval_replay import evaluate_replay_scenarios
from dual_agents.controller import WorkflowViolation, validate_forum_ruling
from dual_agents.opencode_assets import build_agent_markdown
from dual_agents.workflow import WorkflowStage


@dataclass(frozen=True)
class EvalMetrics:
    robustness_score: int
    malformed_forum_catch_rate: float
    coordinator_prompt_chars: int
    review_prompt_chars: int
    validator_chars: int
    workflow_stage_count: int


def _forum_bad_samples() -> tuple[str, ...]:
    return (
        "Thinking: maybe use forum\nCurrent dispute: x\nPerspectives:\n- a\nModerator ruling: b\nNext bounded action: c",
        "Current dispute: x\nPerspectives:\n- a\n- b\n- c\n- d\nModerator ruling: b\nNext bounded action: c",
        "Current dispute: x\nPerspectives:\n- a\nModerator ruling: b",
    )


def _forum_good_sample() -> str:
    return (
        "Current dispute: The page and feed disagree on max speed.\n"
        "Perspectives:\n"
        "- Page extraction is fresher but low confidence.\n"
        "- Feed value is structured but may be variant-specific.\n"
        "Moderator ruling: Treat the disagreement as unresolved and audit variant ownership before promotion.\n"
        "Next bounded action: Add variant-safety checks for max_speed_mph in the merge policy.\n"
    )


def _count_caught_bad_forum_outputs() -> tuple[int, int]:
    caught = 0
    samples = _forum_bad_samples()
    for sample in samples:
        try:
            validate_forum_ruling(sample)
        except WorkflowViolation:
            caught += 1
    validate_forum_ruling(_forum_good_sample())
    return caught, len(samples)


def _build_metrics(*, forum_enabled: bool) -> EvalMetrics:
    config = default_workflow_config().model_copy(update={"forum_adjudication_enabled": forum_enabled})
    agents = build_agent_markdown(config)
    coordinator_prompt = agents["dual-coordinator.md"]
    review_prompt = build_review_prompt(config)
    validator = build_report_validator_script()

    robustness_score = 0
    if "FORUM_ADJUDICATION" in coordinator_prompt:
        robustness_score += 1
    if "--mode forum" in coordinator_prompt:
        robustness_score += 1
    if "Current dispute:" in coordinator_prompt and "Moderator ruling:" in coordinator_prompt:
        robustness_score += 1
    if "FORUM_ADJUDICATION" in review_prompt:
        robustness_score += 1
    if "one bounded next action" in review_prompt.lower():
        robustness_score += 1
    if forum_enabled:
        caught, total = _count_caught_bad_forum_outputs()
    else:
        caught, total = 0, len(_forum_bad_samples())
    catch_rate = caught / total if total else 0.0

    return EvalMetrics(
        robustness_score=robustness_score,
        malformed_forum_catch_rate=catch_rate,
        coordinator_prompt_chars=len(coordinator_prompt),
        review_prompt_chars=len(review_prompt),
        validator_chars=len(validator),
        workflow_stage_count=len(WorkflowStage),
    )


def evaluate_forum_adjudication() -> dict[str, object]:
    baseline = _build_metrics(forum_enabled=False)
    experiment = _build_metrics(forum_enabled=True)
    replay = evaluate_replay_scenarios()

    robustness_gain = experiment.robustness_score - baseline.robustness_score
    prompt_growth = (
        (experiment.coordinator_prompt_chars - baseline.coordinator_prompt_chars)
        + (experiment.review_prompt_chars - baseline.review_prompt_chars)
    )
    validator_growth = experiment.validator_chars - baseline.validator_chars
    complexity_cost = prompt_growth + validator_growth

    recommended = (
        robustness_gain >= 4
        and experiment.malformed_forum_catch_rate >= 1.0
        and replay["delta"]["scenario_protection_gain"] >= 0.14
        and replay["delta"]["adjudication_applicability_gain"] >= 0.5
        and prompt_growth <= 1200
        and validator_growth <= 900
        and experiment.workflow_stage_count - baseline.workflow_stage_count <= 0
    )

    return {
        "baseline": baseline.__dict__,
        "experiment": experiment.__dict__,
        "delta": {
            "robustness_gain": robustness_gain,
            "malformed_forum_catch_gain": round(
                experiment.malformed_forum_catch_rate - baseline.malformed_forum_catch_rate,
                3,
            ),
            "coordinator_prompt_growth_chars": experiment.coordinator_prompt_chars - baseline.coordinator_prompt_chars,
            "review_prompt_growth_chars": experiment.review_prompt_chars - baseline.review_prompt_chars,
            "validator_growth_chars": validator_growth,
            "complexity_cost_chars": complexity_cost,
        },
        "replay": replay,
        "recommendation": {
            "adopt_forum_adjudication": recommended,
            "reason": (
                "Material robustness gain with bounded prompt growth and better replay protection."
                if recommended
                else "Replay protection or robustness gain is not high enough relative to complexity cost."
            ),
        },
    }


def main() -> None:
    print(json.dumps(evaluate_forum_adjudication(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
