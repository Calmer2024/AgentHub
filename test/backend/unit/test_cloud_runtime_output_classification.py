from app.services.cloud_agent_runtime import (
    _is_fatal_cli_output,
    _should_log_cli_output,
    _should_trace_cli_output,
    _trace_kind_for_cli_output,
)


def test_cloud_runtime_text_output_is_not_trace_or_runtime_log():
    assert _should_trace_cli_output("text", None) is False
    assert _should_log_cli_output("text") is False


def test_cloud_runtime_progress_without_structured_trace_is_not_trace():
    assert _should_trace_cli_output("progress", None) is False


def test_cloud_runtime_structured_tool_progress_is_trace():
    assert _should_trace_cli_output("progress", {"kind": "tool"}) is True
    assert _trace_kind_for_cli_output("progress") == "progress"


def test_cloud_runtime_fatal_cli_output_is_detected():
    assert _is_fatal_cli_output(
        "stream disconnected before completion: Concurrency limit exceeded for account"
    )
    assert _should_trace_cli_output("error", None) is True
    assert _should_log_cli_output("error") is True
