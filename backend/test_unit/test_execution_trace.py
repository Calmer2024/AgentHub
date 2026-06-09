from app.services.execution_trace import ExecutionTraceBuilder, MAX_TRACE_ITEMS


def test_execution_trace_records_total_count_when_truncated():
    trace = ExecutionTraceBuilder(
        agent_name="测试工程师",
        cli_tool="codex",
        workspace_path="D:/workspace",
    )

    for index in range(MAX_TRACE_ITEMS + 7):
        trace.add(kind="progress", text=f"过程 {index}")

    metadata = trace.metadata()["executionTrace"]

    assert len(metadata["items"]) == MAX_TRACE_ITEMS
    assert metadata["totalItemCount"] == MAX_TRACE_ITEMS + 7
    assert metadata["truncated"] is True
    assert metadata["items"][0]["text"] == "过程 7"
