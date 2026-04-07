from dual_agents.stop_monitor import StopCategory, classify_stop, format_stop_report


def test_classify_stop_timeout() -> None:
    signal = classify_stop("Error: SSE read timed out")
    assert signal.category == StopCategory.STREAM_TIMEOUT
    assert signal.requires_fresh_session is True


def test_classify_stop_background_service() -> None:
    signal = classify_stop("$ python -m http.server 8000 --directory . &")
    assert signal.category == StopCategory.BACKGROUND_SERVICE
    assert signal.requires_fresh_session is False


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
