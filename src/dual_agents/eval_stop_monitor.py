from __future__ import annotations

import json

from dual_agents.stop_monitor import StopCategory, classify_stop


SCENARIOS: tuple[tuple[str, StopCategory], ...] = (
    (
        "$ python .dual-agents/preflight_stage.py --path robots.txt\n"
        "ERROR: repository contains unrelated dirty files; isolate the unit in a worktree or use a narrower explicit file list.\n"
        "$ git add robots.txt sitemap.xml",
        StopCategory.PREFLIGHT_BYPASS,
    ),
    (
        "$ git status --short\n"
        " M index.html\n"
        "?? data/intro_cache/foo.txt\n"
        "$ git add index.html data/intro_cache/\n"
        "Error: SSE read timed out",
        StopCategory.DIRTY_REPO_STAGE_OVERLOAD,
    ),
    ("Error: SSE read timed out", StopCategory.STREAM_TIMEOUT),
    (
        "Error: The task tool was called with invalid arguments: expected string, received undefined path subagent_type",
        StopCategory.TOOL_SCHEMA_ERROR,
    ),
    (
        "Error: Was there a typo in the url or port?",
        StopCategory.TARGET_ENDPOINT_ERROR,
    ),
    (
        "Thinking: let me gather the data\n<parameter name=\"x\">\nzsh:1: unmatched \"",
        StopCategory.OUTPUT_CORRUPTION,
    ),
    (
        "Traceback (most recent call last):\nAttributeError: 'str' object has no attribute 'get'",
        StopCategory.DATA_SHAPE_MISMATCH,
    ),
    (
        "I can't view images or screenshots - this model doesn't support image input.",
        StopCategory.CAPABILITY_MISMATCH,
    ),
    (
        "Error: The task tool was called with invalid arguments: expected string, received undefined path subagent_type\n"
        "Error: SSE read timed out",
        StopCategory.SESSION_DEGRADATION,
    ),
)


def evaluate_stop_monitor() -> dict[str, object]:
    correct = 0
    results = []
    for sample, expected in SCENARIOS:
        signal = classify_stop(sample)
        ok = signal.category == expected
        correct += int(ok)
        results.append(
            {
                "expected": expected.value,
                "actual": signal.category.value,
                "requires_fresh_session": signal.requires_fresh_session,
                "ok": ok,
            }
        )
    return {
        "scenario_count": len(SCENARIOS),
        "classification_accuracy": round(correct / len(SCENARIOS), 3),
        "results": results,
    }


if __name__ == "__main__":
    print(json.dumps(evaluate_stop_monitor(), indent=2, sort_keys=True))
