from dual_agents.stop_monitor import StopCategory, classify_stop, format_stop_report


def test_classify_stop_dirty_repo_stage_overload() -> None:
    signal = classify_stop(
        "$ git status --short\n"
        " M index.html\n"
        "?? data/intro_cache/foo.txt\n"
        "$ git add index.html data/intro_cache/\n"
        "Error: SSE read timed out\n"
    )
    assert signal.category == StopCategory.DIRTY_REPO_STAGE_OVERLOAD
    assert "worktree" in signal.recovery.lower()


def test_classify_stop_timeout() -> None:
    signal = classify_stop("Error: SSE read timed out")
    assert signal.category == StopCategory.STREAM_TIMEOUT
    assert signal.requires_fresh_session is True


def test_classify_stop_tool_schema_error() -> None:
    signal = classify_stop("Error: expected string, received undefined path subagent_type")
    assert signal.category == StopCategory.TOOL_SCHEMA_ERROR


def test_classify_stop_target_endpoint_error() -> None:
    signal = classify_stop("Error: Was there a typo in the url or port?")
    assert signal.category == StopCategory.TARGET_ENDPOINT_ERROR
    assert "endpoint preflight" in signal.recovery.lower()


def test_classify_stop_analysis_syntax_error_uses_schema_recovery() -> None:
    signal = classify_stop("SyntaxError: invalid syntax")
    assert signal.category == StopCategory.DATA_SHAPE_MISMATCH
    assert "Inspect schema, fix parser" in signal.recovery


def test_classify_stop_detects_session_degradation_from_multiple_signals() -> None:
    signal = classify_stop(
        "Error: The task tool was called with invalid arguments: expected string, received undefined path subagent_type\n"
        "Thinking: let me keep going\n"
        "Error: SSE read timed out"
    )
    assert signal.category == StopCategory.SESSION_DEGRADATION
    assert StopCategory.STREAM_TIMEOUT in signal.matched_categories


def test_format_stop_report_contains_expected_sections() -> None:
    report = format_stop_report(classify_stop("Error: SSE read timed out"), unit_name="pilot kingbull")
    assert "Current unit: pilot kingbull" in report
    assert "Stop signal: STREAM_TIMEOUT" in report
    assert "Next recovery step:" in report
