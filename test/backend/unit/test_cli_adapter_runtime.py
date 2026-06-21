import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.cli_adapters import (
    ClaudeCodeAdapter,
    CliAgentAdapter,
    CodexAdapter,
    OpenCodeAdapter,
    _agent_with_runtime_config,
)
from app.agents.cli_output_parser import CliOutputParser
from app.agents.cli_rpc_session_runtime import (
    CliRpcSessionConfig,
    CliRpcSessionRuntime,
    CliRpcTurnRequest,
)
from app.agents.cli_runtime import CliProcessManager, cli_process_manager
from app.agents.cli_stream import PromptInterceptor, StreamSanitizer
from app.agents.cli_session_runtime import CliSessionProcessConfig, CliSessionProcessRuntime
from app.services.streaming_text import iter_stream_pieces
from app.models import AgentConfig


@pytest.mark.asyncio
async def test_cli_process_manager_reports_unsupported_subprocess_loop(monkeypatch):
    async def raise_not_implemented(*args, **kwargs):
        raise NotImplementedError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", raise_not_implemented)
    manager = CliProcessManager()

    with pytest.raises(RuntimeError) as exc:
        async for _ in manager.stream(
            session_id="session-1",
            agent_id="agent-1",
            executable=sys.executable,
            args=["-c", "print(1)"],
            env_vars={},
            cwd=str(Path.cwd()),
            prompt="",
        ):
            pass

    assert "不支持启动 CLI 子进程" in str(exc.value)


def test_stream_sanitizer_removes_ansi_and_carriage_returns():
    assert StreamSanitizer.clean("\x1b[31mError\x1b[0m\rDone") == "Error\nDone"


def test_stream_sanitizer_removes_split_osc_and_opentui_residue():
    sanitizer = StreamSanitizer()
    assert sanitizer.clean_chunk("\x1b]1337;Capabilities") == ""
    assert sanitizer.clean_chunk("66;w=1\x1b\\OpenCode visible") == "OpenCode visible"

    noisy = (
        "10;?11;?99;i=opentui-notifications:p=?;1337;Capabilities66;w=1; "
        "OpenCode [0m ▄ Update Available esc A new release v1.17.0 is available."
    )
    cleaned = StreamSanitizer.clean(noisy)

    assert "opentui" not in cleaned
    assert "1337;Capabilities" not in cleaned
    assert "[0m" not in cleaned
    assert "Update Available" not in cleaned


def test_prompt_interceptor_detects_confirm_prompt_across_chunks():
    interceptor = PromptInterceptor()
    assert interceptor.detect("Do you want") is None
    assert interceptor.detect(" to run this? (y/n)") == "Do you want to run this? (y/n)"


def test_claude_stream_json_text_and_tool_progress():
    adapter = ClaudeCodeAdapter()
    text = adapter.parse_json_event({
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "tool_use", "name": "Write", "input": {
                    "file_path": "index.html",
                    "content": "<h1>Hi</h1>",
                }},
            ],
        },
    }, seen_text=False)
    assert [(item.text, item.chunk_type) for item in text] == [
        ("hello", "text"),
        ("Claude Code 调用工具: Write", "progress"),
    ]
    assert text[1].trace["kind"] == "tool"
    assert text[1].trace["action"] == "write"
    assert text[1].trace["target"] == "index.html"


def test_claude_stream_event_text_delta_is_streamed_immediately():
    adapter = ClaudeCodeAdapter()
    parsed = adapter.parse_json_event({
        "type": "stream_event",
        "event": {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "TRACE"},
        },
    }, seen_text=False)

    assert len(parsed) == 1
    assert parsed[0].chunk_type == "text"
    assert parsed[0].text == "TRACE"


def test_claude_build_prompt_preserves_agenthub_system_context():
    adapter = ClaudeCodeAdapter()

    prompt = adapter.build_prompt(
        "[Primary Skill: grill-me]\nInterview the user relentlessly.",
        "User:\n哈喽，你是什么角色Agent？\n",
    )

    assert "<agenthub_system_context>" in prompt
    assert "[Primary Skill: grill-me]" in prompt
    assert "Agent Profile 身份" in prompt
    assert "User:\n哈喽，你是什么角色Agent？" in prompt


def test_claude_invocation_normalizes_print_args_and_keeps_session_persistence():
    adapter = ClaudeCodeAdapter()

    args, stdin_prompt, close_stdin = adapter.prepare_invocation(
        ["--no-session-persistence", "--output-format", "stream-json"],
        "hello",
    )

    assert "-p" in args
    assert "--verbose" in args
    assert "--include-partial-messages" in args
    assert "--no-session-persistence" not in args
    assert args.count("--output-format") == 1
    assert stdin_prompt == "hello"
    assert close_stdin is True


def test_claude_invocation_resumes_existing_engine_session():
    adapter = ClaudeCodeAdapter()

    args, _, _ = adapter.prepare_invocation(
        ["-p", "--resume", "old-session", "--session-id", "old-id"],
        "hello",
        engine_session_id="engine-session-1",
    )

    assert "--resume" in args
    assert args[args.index("--resume") + 1] == "engine-session-1"
    assert "old-session" not in args
    assert "--session-id" not in args
    assert "-p" in args


def test_claude_invocation_starts_with_agenthub_assigned_session_id():
    adapter = ClaudeCodeAdapter()

    args, stdin_prompt, close_stdin = adapter.prepare_invocation(
        ["-p", "--resume", "old-session", "--session-id", "old-id"],
        "hello",
        engine_session_id="11111111-1111-4111-8111-111111111111",
        engine_session_mode="start",
    )

    assert "--session-id" in args
    assert args[args.index("--session-id") + 1] == "11111111-1111-4111-8111-111111111111"
    assert "--resume" not in args
    assert "old-session" not in args
    assert "old-id" not in args
    assert stdin_prompt == "hello"
    assert close_stdin is True


def test_claude_persistent_invocation_uses_streaming_input_jsonl():
    adapter = ClaudeCodeAdapter()

    assert adapter.supports_persistent_process is True
    assert adapter.persistent_process_policy.protocol == "stdio_jsonl"

    args, stdin_prompt = adapter.prepare_persistent_invocation(
        [
            "-p",
            "--output-format",
            "stream-json",
            "--input-format",
            "text",
            "--session-id",
            "old-id",
        ],
        "hello persistent",
        engine_session_id="11111111-1111-4111-8111-111111111111",
        engine_session_mode="start",
    )
    payload = json.loads(stdin_prompt)

    assert "-p" in args
    assert "--input-format" in args
    assert args[args.index("--input-format") + 1] == "stream-json"
    assert args.count("--input-format") == 1
    assert "--output-format" in args
    assert args[args.index("--output-format") + 1] == "stream-json"
    assert "--session-id" in args
    assert args[args.index("--session-id") + 1] == "11111111-1111-4111-8111-111111111111"
    assert payload == {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "hello persistent"}],
        },
    }
    assert stdin_prompt.endswith("\n")


def test_claude_persistent_turn_boundary_uses_result_event():
    adapter = ClaudeCodeAdapter()

    assert adapter.persistent_turn_completed('{"type":"assistant"}') is False
    assert adapter.persistent_turn_completed('{"type":"result","session_id":"s1"}') is True
    assert adapter.persistent_turn_completed("not json") is False


def test_claude_invocation_resume_cleanup_preserves_following_flags():
    adapter = ClaudeCodeAdapter()

    args, _, _ = adapter.prepare_invocation(
        ["-p", "--resume", "--verbose", "--continue"],
        "hello",
        engine_session_id="engine-session-1",
    )

    assert "--verbose" in args
    assert "--continue" not in args
    assert args[args.index("--resume") + 1] == "engine-session-1"


def test_claude_result_captures_engine_session_metadata():
    adapter = ClaudeCodeAdapter()

    parsed = adapter.parse_json_event({
        "type": "result",
        "session_id": "engine-session-1",
        "total_cost_usd": 0.01,
        "duration_ms": 1234,
        "num_turns": 2,
    }, seen_text=True)

    assert parsed[0].chunk_type == "metadata"
    assert parsed[0].metadata["engineSessionId"] == "engine-session-1"
    assert parsed[0].metadata["totalCostUsd"] == 0.01


def test_codex_invocation_resumes_existing_engine_session():
    adapter = CodexAdapter()

    args, stdin_prompt, close_stdin = adapter.prepare_invocation(
        [
            "exec",
            "-c",
            'model="gpt-5.5"',
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
            "--color",
            "never",
            "--json",
            "-",
            "-C",
            "D:/workspace",
        ],
        "hello codex",
        engine_session_id="codex-session-1",
    )

    assert args[:2] == ["exec", "resume"]
    assert args[-2:] == ["codex-session-1", "-"]
    assert "--json" in args
    assert "--skip-git-repo-check" in args
    assert "--dangerously-bypass-approvals-and-sandbox" in args
    assert "-c" in args
    assert "--color" not in args
    assert "never" not in args
    assert "-C" not in args
    assert "D:/workspace" not in args
    assert stdin_prompt == "hello codex"
    assert close_stdin is True


def test_codex_prepared_docker_invocation_resumes_inside_container():
    adapter = CodexAdapter()

    args, stdin_prompt, close_stdin = adapter.prepare_prepared_invocation(
        [
            "run",
            "--rm",
            "-i",
            "--name",
            "agenthub-sbx-run",
            "--workdir",
            "/workspace",
            "agenthub-runtime",
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
            "--color",
            "never",
            "--json",
            "-",
            "-C",
            "/workspace",
        ],
        "hello codex",
        engine_session_id="codex-session-1",
    )

    codex_index = args.index("codex")
    assert args[:codex_index] == [
        "run",
        "--rm",
        "-i",
        "--name",
        "agenthub-sbx-run",
        "--workdir",
        "/workspace",
        "agenthub-runtime",
    ]
    assert args[codex_index + 1:codex_index + 3] == ["exec", "resume"]
    assert args[-2:] == ["codex-session-1", "-"]
    assert "--skip-git-repo-check" in args[codex_index + 1:]
    assert "--dangerously-bypass-approvals-and-sandbox" in args[codex_index + 1:]
    assert "--color" not in args[codex_index + 1:]
    assert "never" not in args[codex_index + 1:]
    assert "-C" not in args[codex_index + 1:]
    assert stdin_prompt == "hello codex"
    assert close_stdin is True


def test_codex_runtime_config_preserves_prepared_invocation_flags():
    agent = SimpleNamespace(
        id="agent-1",
        name="Codex",
        cli_tool="codex",
        executable="/usr/bin/docker",
        prepared_invocation=True,
        close_stdin_after_prompt=True,
    )

    runtime_agent = _agent_with_runtime_config(
        agent,
        ["run", "agenthub-runtime", "codex", "exec", "--json", "-"],
        {"OPENAI_API_KEY": "test-key"},
    )

    assert runtime_agent.prepared_invocation is True
    assert runtime_agent.close_stdin_after_prompt is True
    assert runtime_agent.cli_tool == "codex"


def test_codex_thread_event_captures_engine_session_metadata():
    adapter = CodexAdapter()

    parsed = adapter.parse_json_event({
        "type": "thread.started",
        "thread_id": "codex-thread-1",
    }, seen_text=False)

    assert parsed[0].chunk_type == "metadata"
    assert parsed[0].metadata["engineSessionId"] == "codex-thread-1"
    assert parsed[0].metadata["engineSessionSource"] == "codex_thread.started"
    assert parsed[0].metadata["cliTool"] == "codex"


def test_claude_tool_result_has_structured_output_trace():
    adapter = ClaudeCodeAdapter()
    parsed = adapter.parse_json_event({
        "type": "user",
        "message": {
            "content": [{
                "type": "tool_result",
                "tool_use_id": "call_1",
                "content": "1\tTRACE_NOTE\n",
            }],
        },
        "tool_use_result": {
            "type": "text",
            "file": {
                "filePath": "D:/tmp/note.txt",
                "content": "TRACE_NOTE\n",
            },
        },
    }, seen_text=False)

    assert parsed[0].chunk_type == "progress"
    assert parsed[0].trace["kind"] == "file"
    assert parsed[0].trace["target"] == "D:/tmp/note.txt"
    assert "TRACE_NOTE" in parsed[0].trace["detail"]


def test_codex_json_message_text_is_not_raw_json():
    adapter = CodexAdapter()
    parsed = adapter.parse_json_event({
        "type": "message_delta",
        "role": "assistant",
        "delta": "hello",
    }, seen_text=False)
    assert len(parsed) == 1
    assert parsed[0].text == "hello"
    assert parsed[0].chunk_type == "text"


def test_visible_cli_text_is_split_into_readable_stream_pieces():
    text = "第一段内容很长，需要在前端逐步出现。\n第二段继续输出，让用户能感知 Agent 正在回复。"
    pieces = list(iter_stream_pieces(text, target_size=12, max_size=24))

    assert "".join(pieces) == text
    assert len(pieces) > 1


def test_visible_cli_text_splits_long_cjk_without_spaces():
    text = "这是一个没有空格的长中文段落用于模拟CLI一次性返回的大块可见文本"
    pieces = list(iter_stream_pieces(text, target_size=8, max_size=10))

    assert "".join(pieces) == text
    assert all(len(piece) <= 10 for piece in pieces)


def test_codex_lifecycle_json_events_are_hidden_from_user_trace():
    adapter = CodexAdapter()

    assert adapter.parse_json_event({"type": "thread.started"}, seen_text=False) == []
    assert adapter.parse_json_event({"type": "turn.started"}, seen_text=False) == []


def test_codex_raw_lifecycle_lines_are_hidden_from_user_trace():
    adapter = CodexAdapter()

    assert adapter.parse_raw_line("thread.started") == []
    assert adapter.parse_raw_line("turn.started") == []


def test_codex_command_event_has_structured_trace():
    adapter = CodexAdapter()
    parsed = adapter.parse_json_event({
        "type": "exec_command",
        "item": {"type": "exec_command", "command": "rg executionTrace frontend/src"},
    }, seen_text=True)

    assert parsed[0].chunk_type == "progress"
    assert parsed[0].trace["kind"] == "command"
    assert parsed[0].trace["command"] == "rg executionTrace frontend/src"


def test_codex_command_execution_event_includes_status_exit_and_output():
    adapter = CodexAdapter()
    parsed = adapter.parse_json_event({
        "type": "item.completed",
        "item": {
            "id": "item_0",
            "type": "command_execution",
            "command": "pwsh -Command Get-Content note.txt",
            "aggregated_output": "TRACE_NOTE\n",
            "exit_code": 0,
            "status": "completed",
        },
    }, seen_text=True)

    assert parsed[0].chunk_type == "progress"
    assert parsed[0].trace["kind"] == "command"
    assert parsed[0].trace["title"] == "Codex 完成命令"
    assert parsed[0].trace["command"] == "pwsh -Command Get-Content note.txt"
    assert parsed[0].trace["exitCode"] == 0
    assert parsed[0].trace["output"] == "TRACE_NOTE"
    assert "TRACE_NOTE" in parsed[0].trace["detail"]


def test_codex_stderr_multiline_test_failure_stays_one_trace_item():
    adapter = CodexAdapter()
    parsed = adapter.parse_stderr_output(
        """Test timeout of 30000ms exceeded.
Error: locator.click: Test timeout of 30000ms exceeded.

Call log:
- waiting for getByRole('button', { name: '生成预约
提示' })

49 | await page.goto("/", { waitUntil: "domcontentloaded" });
> 50 | await page.getByRole("button", { name: "生成预约提示" }).click();
     |                                                        ^
51 |
"""
    )

    assert len(parsed) == 1
    assert parsed[0].chunk_type == "error"
    assert parsed[0].trace["kind"] == "error"
    assert parsed[0].trace["title"] == "执行超时"
    assert "Call log" in parsed[0].trace["detail"]
    assert "生成预约提示" in parsed[0].trace["detail"]
    assert "> 50 |" in parsed[0].trace["detail"]


def test_codex_raw_model_list_fragment_is_hidden():
    adapter = CodexAdapter()

    assert adapter.parse_raw_line(
        '5200,"owned_by":"openai","type":"model","display_name":"GPT Image 1"}],"object":"list"}'
    ) == []


def test_opencode_json_text_part_is_not_raw_json():
    adapter = OpenCodeAdapter()
    parsed = adapter.parse_json_event({
        "type": "text",
        "part": {
            "type": "text",
            "text": "hello",
        },
    }, seen_text=False)
    assert len(parsed) == 1
    assert parsed[0].text == "hello"
    assert parsed[0].chunk_type == "text"


def test_opencode_tool_part_has_structured_trace():
    adapter = OpenCodeAdapter()
    parsed = adapter.parse_json_event({
        "type": "part",
        "part": {
            "type": "tool",
            "tool": "bash",
            "input": {
                "command": "npm test",
                "cwd": "D:/Files/AI/AgentHub/frontend",
            },
        },
    }, seen_text=False)

    assert parsed[0].chunk_type == "progress"
    assert parsed[0].trace["kind"] == "command"
    assert parsed[0].trace["command"] == "npm test"
    assert parsed[0].trace["target"] == "D:/Files/AI/AgentHub/frontend"


def test_opencode_acp_thought_chunk_is_hidden_from_trace():
    adapter = OpenCodeAdapter()
    parsed = adapter.parse_json_event({
        "sessionUpdate": "agent_thought_chunk",
        "content": {"type": "text", "text": "update the todo and inform the user."},
    }, seen_text=False)

    assert parsed == []


def test_opencode_acp_tool_call_has_structured_trace():
    adapter = OpenCodeAdapter()
    parsed = adapter.parse_json_event({
        "sessionUpdate": "tool_call",
        "kind": "bash",
        "title": "bash",
        "input": {"command": "cat > genshin.html"},
    }, seen_text=False)

    assert parsed[0].chunk_type == "progress"
    assert parsed[0].trace["kind"] == "command"
    assert parsed[0].trace["toolName"] == "bash"
    assert parsed[0].trace["command"] == "cat > genshin.html"


def test_opencode_tool_state_extracts_file_path_and_output():
    adapter = OpenCodeAdapter()
    parsed = adapter.parse_json_event({
        "type": "part",
        "part": {
            "type": "tool",
            "tool": "read",
            "state": {
                "status": "completed",
                "input": {"filePath": "D:/tmp/note.txt"},
                "output": "<content>TRACE_NOTE</content>",
            },
        },
    }, seen_text=False)

    assert parsed[0].chunk_type == "progress"
    assert parsed[0].trace["kind"] == "tool"
    assert parsed[0].trace["target"] == "D:/tmp/note.txt"
    assert parsed[0].trace["status"] == "completed"
    assert "TRACE_NOTE" in parsed[0].trace["output"]


def test_opencode_invocation_passes_prompt_as_run_message():
    adapter = OpenCodeAdapter()
    args, stdin_prompt, close_stdin = adapter.prepare_invocation(
        ["run", "--format", "json", "--dangerously-skip-permissions"],
        "hello opencode",
    )

    assert args == [
        "run",
        "--pure",
        "--agent",
        "build",
        "--format",
        "json",
        "--dangerously-skip-permissions",
        "hello opencode",
    ]
    assert stdin_prompt == ""
    assert close_stdin is True


def test_opencode_invocation_upgrades_legacy_default_args():
    adapter = OpenCodeAdapter()
    args, stdin_prompt, close_stdin = adapter.prepare_invocation(
        ["--no-color", "--plain"],
        "hello opencode",
    )

    assert args == [
        "run",
        "--pure",
        "--agent",
        "build",
        "--format",
        "json",
        "--dangerously-skip-permissions",
        "hello opencode",
    ]
    assert stdin_prompt == ""
    assert close_stdin is True


def test_opencode_invocation_keeps_explicit_message():
    adapter = OpenCodeAdapter()
    args, _, _ = adapter.prepare_invocation(
        [
            "run",
            "--format",
            "json",
            "--dangerously-skip-permissions",
            "prebuilt message",
        ],
        "runtime prompt",
    )

    assert args[-1] == "prebuilt message"
    assert "runtime prompt" not in args


def test_opencode_invocation_resumes_existing_engine_session():
    adapter = OpenCodeAdapter()
    args, stdin_prompt, close_stdin = adapter.prepare_invocation(
        [
            "run",
            "--continue",
            "--session",
            "old-session",
            "--format",
            "json",
            "--dangerously-skip-permissions",
        ],
        "hello opencode",
        engine_session_id="ses_new",
    )

    assert args[:3] == ["run", "--session", "ses_new"]
    assert "--continue" not in args
    assert "old-session" not in args
    assert args[-1] == "hello opencode"
    assert stdin_prompt == ""
    assert close_stdin is True


def test_opencode_prepared_docker_invocation_appends_run_message():
    adapter = OpenCodeAdapter()
    args, stdin_prompt, close_stdin = adapter.prepare_prepared_invocation(
        [
            "run",
            "--rm",
            "-i",
            "agenthub-runtime",
            "opencode",
            "run",
            "--pure",
            "--format",
            "json",
            "--dangerously-skip-permissions",
        ],
        "hello opencode\n",
    )

    assert args[-1] == "hello opencode\n"
    assert stdin_prompt == ""
    assert close_stdin is True


def test_opencode_session_event_captures_engine_session_metadata():
    adapter = OpenCodeAdapter()

    parsed = adapter.parse_json_event({
        "type": "session.created",
        "session": {"id": "ses_abc123"},
    }, seen_text=False)

    assert parsed[0].chunk_type == "metadata"
    assert parsed[0].metadata["engineSessionId"] == "ses_abc123"
    assert parsed[0].metadata["engineSessionSource"] == "opencode_session.created"
    assert parsed[0].metadata["cliTool"] == "opencode"


def test_opencode_acp_command_list_update_is_hidden():
    adapter = OpenCodeAdapter()

    parsed = adapter.parse_json_event({
        "sessionUpdate": "available_commands_update",
        "availableCommands": [{"name": "agenthub-module-dev"}],
    }, seen_text=False)

    assert parsed == []


def test_codex_fatal_stdout_line_is_error_chunk():
    adapter = CodexAdapter()
    parsed = adapter.parse_raw_line(
        "stream disconnected before completion: Concurrency limit exceeded for account, please retry later"
    )

    assert parsed[0].chunk_type == "error"
    assert parsed[0].trace["kind"] == "error"


def test_codex_status_event_has_progress_trace():
    adapter = CodexAdapter()
    parsed = adapter.parse_json_event({
        "type": "status",
        "item": {
            "type": "status",
            "status": "running",
            "title": "Codex 仍在执行",
            "message": "Codex MCP 请求仍在运行，已等待 20 秒。",
            "elapsedSeconds": 20,
        },
    }, seen_text=False)

    assert parsed[0].chunk_type == "progress"
    assert parsed[0].trace["kind"] == "progress"
    assert parsed[0].trace["title"] == "Codex 仍在执行"
    assert "已等待 20 秒" in parsed[0].trace["detail"]


def test_codex_prefers_exec_json_streaming_over_persistent_rpc_by_default():
    adapter = CodexAdapter()

    assert adapter.supports_persistent_process is False
    assert adapter.persistent_process_policy.protocol == "mcp"
    assert adapter.supports_engine_session_resume is True
    assert "exec --json" in adapter.persistent_process_policy.strategy


def test_opencode_renders_latest_user_request_as_direct_message():
    adapter = OpenCodeAdapter()
    prompt = adapter.render_prompt_messages([
        {"role": "user", "content": "Print exactly hello and stop."},
    ])

    assert prompt == "Print exactly hello and stop.\n"


def test_opencode_renders_history_as_context_before_latest_request():
    adapter = OpenCodeAdapter()
    prompt = adapter.render_prompt_messages([
        {"role": "user", "content": "Earlier"},
        {"role": "assistant", "content": "Previous answer"},
        {"role": "user", "content": "Current task"},
    ])

    assert prompt == "Current task\n"
    assert "Earlier" not in prompt
    assert "Previous answer" not in prompt


def test_opencode_uses_latest_user_message_even_if_assistant_is_last():
    adapter = OpenCodeAdapter()
    prompt = adapter.render_prompt_messages([
        {"role": "user", "content": "Earlier"},
        {"role": "user", "content": "Current task"},
        {"role": "assistant", "content": "Stale assistant answer"},
    ])

    assert prompt == "Current task\n"
    assert "Stale assistant answer" not in prompt


def test_codex_persistent_rpc_invocation_uses_mcp_server_tool_call():
    adapter = CodexAdapter()

    args, request = adapter.prepare_persistent_rpc_invocation(
        [
            "exec",
            "-c",
            'model="gpt-5"',
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
            "--json",
            "-",
        ],
        "hello codex",
        system_prompt="system note",
        cwd="D:/workspace",
    )

    assert args == ["mcp-server", "-c", 'model="gpt-5"']
    assert request.method == "tools/call"
    assert request.params["name"] == "codex"
    assert request.params["arguments"]["prompt"] == "hello codex"
    assert request.params["arguments"]["cwd"] == "D:/workspace"
    assert request.params["arguments"]["developer-instructions"] == "system note"
    assert request.params["arguments"]["sandbox"] == "danger-full-access"
    assert request.params["arguments"]["approval-policy"] == "never"
    assert request.params["arguments"]["config"]["skip_git_repo_check"] is True
    assert request.resume_method == "tools/call"
    assert request.resume_params["name"] == "codex-reply"
    assert request.native_session_param == "arguments.threadId"


def test_codex_persistent_rpc_invocation_preserves_docker_wrapper():
    adapter = CodexAdapter()

    args, request = adapter.prepare_persistent_rpc_invocation(
        [
            "run",
            "--rm",
            "-i",
            "--workdir",
            "/workspace",
            "--mount",
            "type=bind,source=D:/host,target=/workspace",
            "agenthub-runtime",
            "codex",
            "exec",
            "-c",
            'model="gpt-5"',
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
            "--json",
            "-",
        ],
        "hello from cloud",
        cwd="D:/host",
    )

    assert args == [
        "run",
        "--rm",
        "-i",
        "--workdir",
        "/workspace",
        "--mount",
        "type=bind,source=D:/host,target=/workspace",
        "agenthub-runtime",
        "codex",
        "mcp-server",
        "-c",
        'model="gpt-5"',
    ]
    assert request.params["arguments"]["prompt"] == "hello from cloud"
    assert request.params["arguments"]["cwd"] == "/workspace"
    assert request.params["arguments"]["sandbox"] == "danger-full-access"
    assert request.params["arguments"]["approval-policy"] == "never"
    assert request.params["arguments"]["config"]["skip_git_repo_check"] is True


def test_opencode_persistent_rpc_invocation_uses_acp_prompt():
    adapter = OpenCodeAdapter()

    args, request = adapter.prepare_persistent_rpc_invocation(
        ["run", "--pure", "--format", "json", "--dangerously-skip-permissions"],
        "hello opencode\n",
        cwd="D:/workspace",
    )

    assert args == ["acp", "--pure", "--cwd", "D:/workspace"]
    assert request.method == "session/prompt"
    assert request.params == {
        "prompt": [{"type": "text", "text": "hello opencode"}],
    }
    assert request.native_session_param == "sessionId"


def test_opencode_persistent_rpc_invocation_preserves_docker_wrapper():
    adapter = OpenCodeAdapter()

    args, request = adapter.prepare_persistent_rpc_invocation(
        [
            "run",
            "--rm",
            "-i",
            "--workdir",
            "/workspace",
            "agenthub-runtime",
            "opencode",
            "run",
            "--pure",
            "--format",
            "json",
            "--dangerously-skip-permissions",
        ],
        "hello opencode\n",
        cwd="D:/host/workspace",
    )

    assert args == [
        "run",
        "--rm",
        "-i",
        "--workdir",
        "/workspace",
        "agenthub-runtime",
        "opencode",
        "acp",
        "--pure",
        "--cwd",
        "/workspace",
    ]
    assert "D:/host/workspace" not in args
    assert request.method == "session/prompt"
    assert request.params["prompt"] == [{"type": "text", "text": "hello opencode"}]


def test_opencode_persistent_rpc_invocation_ignores_tmp_opencode_mount():
    adapter = OpenCodeAdapter()

    args, _request = adapter.prepare_persistent_rpc_invocation(
        [
            "run",
            "--rm",
            "-i",
            "--workdir",
            "/workspace",
            "--mount",
            "type=bind,source=/srv/workspace,target=/workspace",
            "--mount",
            "type=bind,source=/srv/workspace,target=/tmp/opencode",
            "--env-file",
            "/tmp/agenthub-runtime-env/run.env",
            "agenthub-runtime",
            "opencode",
            "run",
            "--pure",
            "--format",
            "json",
        ],
        "hello opencode\n",
        cwd="/srv/workspace",
    )

    assert args == [
        "run",
        "--rm",
        "-i",
        "--workdir",
        "/workspace",
        "--mount",
        "type=bind,source=/srv/workspace,target=/workspace",
        "--mount",
        "type=bind,source=/srv/workspace,target=/tmp/opencode",
        "--env-file",
        "/tmp/agenthub-runtime-env/run.env",
        "agenthub-runtime",
        "opencode",
        "acp",
        "--pure",
        "--cwd",
        "/workspace",
    ]


def test_codex_proxy_settings_become_isolated_one_off_config_overrides():
    adapter = CodexAdapter()
    args, env = adapter._apply_connection_settings(
        [
            "exec",
            "--skip-git-repo-check",
            "--json",
            "-",
        ],
        {
            "AGENTHUB_CODEX_BASE_URL": "https://proxy.example.com/v1",
            "AGENTHUB_CODEX_API_KEY": "proxy-key",
            "AGENTHUB_CODEX_MODEL": "gpt-5.5",
            "CUSTOM_FLAG": "1",
        },
    )

    joined = "\n".join(args)
    assert args[0] == "exec"
    assert 'model="gpt-5.5"' in joined
    assert "--ignore-user-config" in args
    assert 'model_provider="agenthub_proxy"' in joined
    assert 'model_providers.agenthub_proxy.base_url="https://proxy.example.com/v1"' in joined
    assert 'model_providers.agenthub_proxy.env_key="AGENTHUB_CODEX_PROVIDER_TOKEN"' in joined
    assert env == {
        "CUSTOM_FLAG": "1",
        "AGENTHUB_CODEX_PROVIDER_TOKEN": "proxy-key",
    }


def test_codex_proxy_settings_keep_user_provider_id_and_env_key():
    adapter = CodexAdapter()
    args, env = adapter._apply_connection_settings(
        ["exec", "--json", "-"],
        {
            "AGENTHUB_CODEX_CONNECTION": "proxy",
            "AGENTHUB_CODEX_BASE_URL": "https://relay.example.com/custom-api",
            "AGENTHUB_CODEX_API_KEY": "proxy-key",
            "AGENTHUB_CODEX_MODEL": "relay-codex",
            "AGENTHUB_CODEX_PROVIDER_ID": "OpenAI",
            "AGENTHUB_CODEX_PROVIDER_NAME": "OpenAI",
        },
    )

    joined = "\n".join(args)
    assert 'model_provider="OpenAI"' in joined
    assert 'model_providers.OpenAI.name="OpenAI"' in joined
    assert 'model_providers.OpenAI.base_url="https://relay.example.com/custom-api"' in joined
    assert 'model_providers.OpenAI.env_key="AGENTHUB_CODEX_PROVIDER_TOKEN"' in joined
    assert env == {"AGENTHUB_CODEX_PROVIDER_TOKEN": "proxy-key"}


def test_codex_proxy_settings_preserve_gateway_base_url():
    adapter = CodexAdapter()
    args, _ = adapter._apply_connection_settings(
        ["exec", "--json", "-"],
        {
            "AGENTHUB_CODEX_CONNECTION": "proxy",
            "AGENTHUB_CODEX_BASE_URL": "https://proxy.example.com",
            "AGENTHUB_CODEX_API_KEY": "proxy-key",
        },
    )

    joined = "\n".join(args)
    assert 'model_providers.agenthub_proxy.base_url="https://proxy.example.com"' in joined


def test_codex_proxy_requires_scoped_api_key():
    adapter = CodexAdapter()
    with pytest.raises(ValueError, match="中转 API Key"):
        adapter._apply_connection_settings(
            ["exec", "--json", "-"],
            {
                "AGENTHUB_CODEX_CONNECTION": "proxy",
                "AGENTHUB_CODEX_BASE_URL": "https://proxy.example.com/v1",
            },
        )


def test_codex_auto_detects_proxy_provider_from_codex_home(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        'model = "gpt-5.5"\n'
        'model_provider = "proxy"\n'
        '[model_providers.proxy]\n'
        'name = "Local Proxy"\n'
        'base_url = "https://proxy.example.com"\n'
        'wire_api = "responses"\n'
        'env_key = "OPENAI_API_KEY"\n',
        encoding="utf-8",
    )
    (codex_home / ".env").write_text("OPENAI_API_KEY=proxy-key\n", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    args, env = CodexAdapter()._apply_connection_settings(["exec", "--json", "-"], {})

    assert args == ["exec", "--json", "-"]
    assert env == {"OPENAI_API_KEY": "proxy-key"}


def test_codex_auto_detects_command_backed_proxy_auth(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    helper = codex_home / "agenthub" / "codex-auth-helper.ps1"
    helper.parent.mkdir()
    helper.write_text("param([string]$Name)\n", encoding="utf-8")
    (codex_home / "config.toml").write_text(
        'model = "gpt-5.5"\n'
        'model_provider = "proxy"\n'
        '[model_providers.proxy]\n'
        'name = "Local Proxy"\n'
        'base_url = "https://proxy.example.com"\n'
        'wire_api = "responses"\n'
        '[model_providers.proxy.auth]\n'
        'command = "powershell.exe"\n'
        f'args = ["-File", "{str(helper).replace("\\", "\\\\")}", "CODEX_API_KEY"]\n',
        encoding="utf-8",
    )
    (codex_home / ".env").write_text("CODEX_API_KEY=proxy-key\n", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    args, env = CodexAdapter()._apply_connection_settings(["exec", "--json", "-"], {})

    assert args == ["exec", "--json", "-"]
    assert env == {"CODEX_API_KEY": "proxy-key"}


def test_codex_auto_detects_official_openai_base_url(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        'model = "gpt-5.5"\n'
        'openai_base_url = "https://api.openai.com/v1"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    args, env = CodexAdapter()._apply_connection_settings(["exec", "--json", "-"], {})

    assert args == ["exec", "--json", "-"]
    assert env == {}


def test_codex_auto_detects_proxy_auth_mismatch(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        'model_provider = "OpenAI"\n'
        '[model_providers.OpenAI]\n'
        'name = "OpenAI"\n'
        'base_url = "https://sub2.congmingai.com"\n'
        'wire_api = "responses"\n'
        'requires_openai_auth = true\n',
        encoding="utf-8",
    )
    (codex_home / "auth.json").write_text(
        '{"auth_mode":"chatgpt","OPENAI_API_KEY":null}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    with pytest.raises(ValueError, match="第三方中转 URL"):
        CodexAdapter()._apply_connection_settings(["exec", "--json", "-"], {})


def test_codex_official_can_use_openai_auth_without_api_key():
    adapter = CodexAdapter()
    args, env = adapter._apply_connection_settings(
        ["exec", "--json", "-"],
        {
            "AGENTHUB_CODEX_CONNECTION": "official",
            "AGENTHUB_CODEX_MODEL": "gpt-5.5",
        },
    )

    joined = "\n".join(args)
    assert "--ignore-user-config" in args
    assert 'model_providers.agenthub_proxy.base_url="https://api.openai.com/v1"' in joined
    assert "requires_openai_auth=true" in joined
    assert "env_key" not in joined
    assert env == {}


def test_codex_inherit_mode_ignores_stale_proxy_fields():
    adapter = CodexAdapter()
    args, env = adapter._apply_connection_settings(
        ["exec", "--json", "-"],
        {
            "AGENTHUB_CODEX_CONNECTION": "inherit",
            "AGENTHUB_CODEX_BASE_URL": "https://proxy.example.com/v1",
            "AGENTHUB_CODEX_API_KEY": "proxy-key",
            "CUSTOM_FLAG": "1",
        },
    )

    assert args == ["exec", "--json", "-"]
    assert env == {"CUSTOM_FLAG": "1"}


def test_json_parser_summarizes_html_stderr_once():
    parser = CliOutputParser(CodexAdapter())
    outputs = parser.feed_stderr("<!doctype html>\n<html><head><title>Gateway</title></head>")
    outputs += parser.feed_stderr("<body>very long login page</body>")
    outputs += parser.feed_stderr("</html>")

    assert len(outputs) == 1
    assert outputs[0].chunk_type == "error"
    assert "Base URL" in outputs[0].text
    assert "very long login page" not in outputs[0].text


def test_codex_stderr_noise_is_suppressed():
    parser = CliOutputParser(CodexAdapter())
    outputs = parser.feed_stderr(
        '2026-06-04T22:30:40.944326Z ERROR codex_models_manager::manager: '
        'failed to refresh available models: failed to decode models response: body: {"data":[]}\n'
        '2026-06-04T22:30:41.010987Z  WARN codex_core::shell_snapshot: '
        'Failed to create shell snapshot for powershell: Shell snapshot not supported yet for PowerShell\n'
        '2026-06-04T22:30:41.182182Z  WARN codex_core_skills::loader: '
        "ignoring interface.icon_small: icon path with '..' must resolve under plugin assets/\n"
        '2026-06-04T22:30:41.345493Z  WARN codex_core_plugins::manifest: '
        'ignoring interface.defaultPrompt[0]: prompt must be at most 128 characters path=plugin.json\n'
    )

    assert outputs == []


def test_codex_split_model_refresh_body_is_suppressed():
    parser = CliOutputParser(CodexAdapter())
    outputs = parser.feed_stderr(
        '2026-06-04T22:30:40.944326Z ERROR codex_models_manager::manager: '
        'failed to refresh available models: failed to decode models response: body: {"data":['
    )
    outputs += parser.feed_stderr('{"id":"gpt-5.5"}')
    outputs += parser.feed_stderr('],"object":"list"}\nReconnecting... 1/5 (temporary network issue)')

    assert len(outputs) == 1
    assert outputs[0].text.startswith("Codex 正在重试连接")
    assert "gpt-5.5" not in outputs[0].text


def test_codex_stderr_keeps_real_errors_after_noise_filtering():
    parser = CliOutputParser(CodexAdapter())
    outputs = parser.feed_stderr(
        '2026-06-04T22:30:41.182182Z  WARN codex_core_skills::loader: '
        "ignoring interface.icon_large: icon path with '..' must resolve under plugin assets/\n"
        "Error: command failed with exit code 1\n"
    )

    assert len(outputs) == 1
    assert outputs[0].chunk_type == "error"
    assert outputs[0].text == "Error: command failed with exit code 1"


@pytest.mark.asyncio
async def test_cli_process_manager_streams_real_subprocess_and_interactive_reply(tmp_path):
    script = _write_interactive_script(tmp_path)
    manager = CliProcessManager()
    events = []
    async for chunk in manager.stream(
        session_id="session-1",
        agent_id="agent-1",
        executable=sys.executable,
        args=[str(script)],
        env_vars={},
        cwd=str(tmp_path),
        prompt="ignored\n",
        close_stdin_after_prompt=False,
        silence_timeout_seconds=5,
    ):
        events.append(chunk)
        if chunk.text and "Do you want to run this? (y/n)" in chunk.text:
            await manager.reply(chunk.process_id, "y")

    text = "".join(event.text for event in events if event.text)
    assert "start" in text
    assert "confirmed" in text
    assert events[-1].event_type == "completed"
    assert events[-1].exit_code == 0


@pytest.mark.asyncio
async def test_cli_process_manager_emits_heartbeat_without_killing_live_process(tmp_path):
    script = _write_silent_then_done_script(tmp_path)
    manager = CliProcessManager()
    events = []

    async for chunk in manager.stream(
        session_id="session-heartbeat",
        agent_id="agent-heartbeat",
        executable=sys.executable,
        args=[str(script)],
        env_vars={},
        cwd=str(tmp_path),
        prompt="ignored\n",
        close_stdin_after_prompt=True,
        silence_timeout_seconds=0.5,
        heartbeat_interval_seconds=0.03,
    ):
        events.append(chunk)

    assert any(event.event_type == "heartbeat" for event in events)
    assert not any(event.event_type == "timeout" for event in events)
    assert "done" in "".join(event.text for event in events if event.text)
    assert events[-1].event_type == "completed"
    assert events[-1].exit_code == 0


@pytest.mark.asyncio
async def test_cli_adapter_maps_heartbeat_to_progress_event(tmp_path):
    script = _write_silent_then_done_script(tmp_path)
    agent = AgentConfig(
        id="agent-heartbeat-adapter",
        name="Heartbeat CLI",
        description="",
        system_prompt="",
        agent_type="cli_wrapper",
        cli_tool="custom",
        executable=sys.executable,
        init_args=f'["{str(script).replace("\\", "\\\\")}"]',
        env_vars="{}",
    )

    class FastHeartbeatAdapter(CliAgentAdapter):
        silence_timeout_seconds = 0.5
        heartbeat_interval_seconds = 0.03

    events = []
    async for event in FastHeartbeatAdapter().stream(
        agent=agent,
        session_id="session-heartbeat-adapter",
        cwd=str(tmp_path),
        user_prompt="ignored\n",
    ):
        events.append(event)

    heartbeat_events = [
        event
        for event in events
        if event.type == "agent.output"
        and event.chunk_type == "progress"
        and event.metadata
        and event.metadata.get("heartbeat")
    ]
    assert heartbeat_events
    assert any(event.type == "agent.process.completed" for event in events)


@pytest.mark.asyncio
async def test_custom_cli_adapter_keeps_stdin_for_interactive_reply(tmp_path):
    script = _write_interactive_script(tmp_path)
    agent = AgentConfig(
        id="agent-custom",
        name="Custom CLI",
        description="",
        system_prompt="",
        agent_type="cli_wrapper",
        cli_tool="custom",
        executable=sys.executable,
        init_args=f'["{str(script).replace("\\", "\\\\")}"]',
        env_vars="{}",
    )
    adapter = CliAgentAdapter()
    events = []

    async for event in adapter.stream(
        agent=agent,
        session_id="session-custom",
        cwd=str(tmp_path),
        user_prompt="ignored\n",
    ):
        events.append(event)
        if event.type == "interactive_prompt":
            await cli_process_manager.reply(event.process_id, "y")

    assert any(event.type == "interactive_prompt" for event in events)
    output = "".join(event.chunk for event in events if event.type == "agent.output")
    assert "confirmed" in output


@pytest.mark.asyncio
async def test_persistent_process_reuses_one_process_for_same_session(tmp_path):
    script = _write_persistent_jsonl_script(tmp_path)
    runtime = CliSessionProcessRuntime()
    first = await _collect_persistent_turn(
        runtime,
        script,
        tmp_path,
        session_id="session-persistent",
        prompt="first\n",
    )
    second = await _collect_persistent_turn(
        runtime,
        script,
        tmp_path,
        session_id="session-persistent",
        prompt="second\n",
    )

    try:
        first_started = first[0]
        second_started = second[0]
        assert first_started.event_type == "started"
        assert second_started.event_type == "started"
        assert first_started.process_id == second_started.process_id
        assert second_started.reused is True
        assert first[-1].event_type == "turn_completed"
        assert second[-1].event_type == "turn_completed"
        snapshots = runtime.active_snapshots("session-persistent")
        assert len(snapshots) == 1
        assert snapshots[0]["persistent"] is True
        assert snapshots[0]["reused"] is True
        assert snapshots[0]["recovered"] is False
        assert snapshots[0]["turnActive"] is False
    finally:
        await runtime.terminate_session("session-persistent")


@pytest.mark.asyncio
async def test_persistent_process_isolated_by_session(tmp_path):
    script = _write_persistent_jsonl_script(tmp_path)
    runtime = CliSessionProcessRuntime()
    first = await _collect_persistent_turn(
        runtime,
        script,
        tmp_path,
        session_id="session-a",
        prompt="first\n",
    )
    second = await _collect_persistent_turn(
        runtime,
        script,
        tmp_path,
        session_id="session-b",
        prompt="second\n",
    )

    try:
        assert first[0].process_id != second[0].process_id
        assert len(runtime.active_snapshots("session-a")) == 1
        assert len(runtime.active_snapshots("session-b")) == 1
    finally:
        await runtime.terminate_session("session-a")
        await runtime.terminate_session("session-b")


@pytest.mark.asyncio
async def test_persistent_process_recovers_after_child_exit(tmp_path):
    script = _write_persistent_jsonl_script(tmp_path)
    runtime = CliSessionProcessRuntime()
    first = await _collect_persistent_turn(
        runtime,
        script,
        tmp_path,
        session_id="session-recover",
        prompt="first\n",
    )
    old_process_id = first[0].process_id
    old_handle = runtime._handles_by_process[old_process_id]
    old_handle.process.kill()
    await old_handle.process.wait()

    second = await _collect_persistent_turn(
        runtime,
        script,
        tmp_path,
        session_id="session-recover",
        prompt="second\n",
    )

    try:
        assert second[0].event_type == "started"
        assert second[0].process_id != old_process_id
        assert second[0].recovered is True
        assert second[-1].event_type == "turn_completed"
        snapshots = runtime.active_snapshots("session-recover")
        assert snapshots[0]["recovered"] is True
    finally:
        await runtime.terminate_session("session-recover")


@pytest.mark.asyncio
async def test_persistent_process_serializes_concurrent_turns_for_same_session(tmp_path):
    script = _write_persistent_jsonl_script(tmp_path)
    runtime = CliSessionProcessRuntime()

    try:
        first_task = asyncio.create_task(_collect_persistent_turn(
            runtime,
            script,
            tmp_path,
            session_id="session-concurrent",
            prompt="first\n",
        ))
        await asyncio.sleep(0.05)
        second_task = asyncio.create_task(_collect_persistent_turn(
            runtime,
            script,
            tmp_path,
            session_id="session-concurrent",
            prompt="second\n",
        ))
        first, second = await asyncio.gather(first_task, second_task)

        text = "\n".join(
            chunk.text
            for chunk in [*first, *second]
            if chunk.text
        )
        assert first[0].process_id == second[0].process_id
        assert "turn=1 first" in text
        assert "turn=2 second" in text
        assert first[-1].event_type == "turn_completed"
        assert second[-1].event_type == "turn_completed"
    finally:
        await runtime.terminate_session("session-concurrent")


@pytest.mark.asyncio
async def test_rpc_session_runtime_reuses_codex_mcp_server_for_replies(tmp_path):
    script = _write_fake_codex_mcp_server(tmp_path)
    runtime = CliRpcSessionRuntime()
    first = await _collect_rpc_turn(
        runtime,
        script,
        tmp_path,
        protocol="mcp",
        session_id="session-rpc-codex",
        cli_tool="codex",
        request=_codex_rpc_turn_request("first"),
    )
    second = await _collect_rpc_turn(
        runtime,
        script,
        tmp_path,
        protocol="mcp",
        session_id="session-rpc-codex",
        cli_tool="codex",
        request=_codex_rpc_turn_request("second"),
    )

    try:
        assert first[0].event_type == "started"
        assert second[0].event_type == "started"
        assert first[0].process_id == second[0].process_id
        assert second[0].reused is True
        assert first[-1].event_type == "turn_completed"
        assert second[-1].event_type == "turn_completed"
        text = "".join(chunk.text for chunk in [*first, *second] if chunk.text)
        assert "mcp:codex:first:thread=thread-1" in text
        assert "mcp:codex-reply:second:thread=thread-1" in text
        snapshots = runtime.active_snapshots("session-rpc-codex")
        assert snapshots[0]["mode"] == "rpc_session"
        assert snapshots[0]["protocol"] == "mcp"
        assert snapshots[0]["nativeSessionId"] == "thread-1"
    finally:
        await runtime.terminate_session("session-rpc-codex")


@pytest.mark.asyncio
async def test_rpc_session_runtime_emits_codex_progress_while_tool_call_is_pending(tmp_path):
    script = _write_fake_codex_mcp_server(tmp_path)
    runtime = CliRpcSessionRuntime()
    chunks = await _collect_rpc_turn(
        runtime,
        script,
        tmp_path,
        protocol="mcp",
        session_id="session-rpc-codex-progress",
        cli_tool="codex",
        request=_codex_rpc_turn_request("slow progress"),
        progress_interval_seconds=0.05,
    )

    try:
        progress_events = [
            json.loads(chunk.text)
            for chunk in chunks
            if chunk.text and '"type": "status"' in chunk.text
        ]
        text = "".join(chunk.text for chunk in chunks if chunk.text)

        assert len(progress_events) >= 2
        assert progress_events[0]["item"]["title"] == "Codex 已接收任务"
        assert any(event["item"]["title"] == "Codex 仍在执行" for event in progress_events)
        assert "mcp:codex:slow progress:thread=thread-1" in text
        assert chunks[-1].event_type == "turn_completed"
    finally:
        await runtime.terminate_session("session-rpc-codex-progress")


@pytest.mark.asyncio
async def test_rpc_session_runtime_codex_progress_does_not_mask_timeout(tmp_path):
    script = _write_fake_codex_mcp_server(tmp_path)
    runtime = CliRpcSessionRuntime()
    chunks = await _collect_rpc_turn(
        runtime,
        script,
        tmp_path,
        protocol="mcp",
        session_id="session-rpc-codex-progress-timeout",
        cli_tool="codex",
        request=_codex_rpc_turn_request("slow timeout"),
        progress_interval_seconds=0.02,
        silence_timeout_seconds=0.08,
    )

    try:
        assert any(chunk.text and '"type": "status"' in chunk.text for chunk in chunks)
        assert chunks[-1].event_type == "timeout"
    finally:
        await runtime.terminate_session("session-rpc-codex-progress-timeout")


@pytest.mark.asyncio
async def test_rpc_session_runtime_streams_opencode_acp_updates(tmp_path):
    script = _write_fake_opencode_acp_server(tmp_path)
    runtime = CliRpcSessionRuntime()
    first = await _collect_rpc_turn(
        runtime,
        script,
        tmp_path,
        protocol="acp",
        session_id="session-rpc-opencode",
        cli_tool="opencode",
        request=_opencode_rpc_turn_request("first"),
    )
    second = await _collect_rpc_turn(
        runtime,
        script,
        tmp_path,
        protocol="acp",
        session_id="session-rpc-opencode",
        cli_tool="opencode",
        request=_opencode_rpc_turn_request("second"),
    )

    try:
        assert first[0].process_id == second[0].process_id
        assert second[0].reused is True
        assert first[-1].event_type == "turn_completed"
        assert second[-1].event_type == "turn_completed"
        text = "".join(chunk.text for chunk in [*first, *second] if chunk.text)
        assert "acp:ses_1:first" in text
        assert "acp:ses_1:second" in text
        snapshots = runtime.active_snapshots("session-rpc-opencode")
        assert snapshots[0]["mode"] == "rpc_session"
        assert snapshots[0]["protocol"] == "acp"
        assert snapshots[0]["nativeSessionId"] == "ses_1"
    finally:
        await runtime.terminate_session("session-rpc-opencode")


def _write_interactive_script(tmp_path: Path) -> Path:
    script = tmp_path / "interactive_cli.py"
    script.write_text(
        "import sys, time\n"
        "sys.stdin.readline()\n"
        "sys.stdout.write('\\x1b[32mstart\\x1b[0m\\n')\n"
        "sys.stdout.write('Do you want to run this? (y/n) ')\n"
        "sys.stdout.flush()\n"
        "reply = sys.stdin.readline().strip()\n"
        "sys.stdout.write('confirmed\\n' if reply == 'y' else 'denied\\n')\n"
        "sys.stdout.flush()\n",
        encoding="utf-8",
    )
    return script


def _write_silent_then_done_script(tmp_path: Path) -> Path:
    script = tmp_path / "silent_then_done.py"
    script.write_text(
        "import sys, time\n"
        "sys.stdin.readline()\n"
        "sys.stdout.write('start\\n')\n"
        "sys.stdout.flush()\n"
        "time.sleep(0.12)\n"
        "sys.stdout.write('done\\n')\n"
        "sys.stdout.flush()\n",
        encoding="utf-8",
    )
    return script


async def _collect_persistent_turn(
    runtime: CliSessionProcessRuntime,
    script: Path,
    tmp_path: Path,
    *,
    session_id: str,
    prompt: str,
):
    events = []
    async for chunk in runtime.stream_turn(
        config=CliSessionProcessConfig(
            session_id=session_id,
            agent_id="agent-persistent",
            executable=sys.executable,
            args=[str(script)],
            env_vars={},
            cwd=str(tmp_path),
        ),
        prompt=prompt,
        silence_timeout_seconds=5,
        turn_completed=_is_result_line,
    ):
        events.append(chunk)
    return events


def _is_result_line(line: str) -> bool:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and data.get("type") == "result"


def _write_persistent_jsonl_script(tmp_path: Path) -> Path:
    script = tmp_path / "persistent_cli.py"
    script.write_text(
        "import json, os, sys\n"
        "turn = 0\n"
        "for line in sys.stdin:\n"
        "    turn += 1\n"
        "    text = line.strip()\n"
        "    sys.stdout.write(json.dumps({\n"
        "        'type': 'assistant',\n"
        "        'message': {'content': [{'type': 'text', 'text': f'pid={os.getpid()} turn={turn} {text}'}]},\n"
        "    }) + '\\n')\n"
        "    sys.stdout.write(json.dumps({\n"
        "        'type': 'result',\n"
        "        'session_id': 'engine-session',\n"
        "        'is_error': False,\n"
        "    }) + '\\n')\n"
        "    sys.stdout.flush()\n",
        encoding="utf-8",
    )
    return script


async def _collect_rpc_turn(
    runtime: CliRpcSessionRuntime,
    script: Path,
    tmp_path: Path,
    *,
    protocol: str,
    session_id: str,
    cli_tool: str,
    request: CliRpcTurnRequest,
    progress_interval_seconds: float | None = None,
    silence_timeout_seconds: float = 5,
):
    events = []
    async for chunk in runtime.stream_turn(
        config=CliRpcSessionConfig(
            session_id=session_id,
            agent_id=f"agent-{cli_tool}",
            executable=sys.executable,
            args=[str(script)],
            env_vars={},
            cwd=str(tmp_path),
            protocol=protocol,
            cli_tool=cli_tool,
        ),
        request=request,
        silence_timeout_seconds=silence_timeout_seconds,
        progress_interval_seconds=progress_interval_seconds,
    ):
        events.append(chunk)
    return events


@pytest.mark.asyncio
async def test_rpc_session_runtime_reads_codex_mcp_jsonl_message():
    reader = asyncio.StreamReader()
    reader.feed_data(b'{"jsonrpc":"2.0","id":"1","result":{"ok":true}}\n')
    reader.feed_eof()

    message = await CliRpcSessionRuntime._read_mcp_message(reader)

    assert message == {"jsonrpc": "2.0", "id": "1", "result": {"ok": True}}


@pytest.mark.asyncio
async def test_rpc_session_runtime_reads_large_codex_mcp_jsonl_message():
    reader = asyncio.StreamReader()
    large_text = "鸣潮" * 40_000
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": "large", "result": {"content": large_text}},
        ensure_ascii=False,
    ).encode("utf-8") + b"\n"
    reader.feed_data(payload)
    reader.feed_eof()

    message = await CliRpcSessionRuntime._read_mcp_message(reader)

    assert message["id"] == "large"
    assert message["result"]["content"] == large_text


@pytest.mark.asyncio
async def test_rpc_session_runtime_reads_mcp_content_length_message():
    reader = asyncio.StreamReader()
    raw = b'{"jsonrpc":"2.0","id":"2","result":{"ok":true}}'
    reader.feed_data(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw)
    reader.feed_eof()

    message = await CliRpcSessionRuntime._read_mcp_message(reader)

    assert message == {"jsonrpc": "2.0", "id": "2", "result": {"ok": True}}


@pytest.mark.asyncio
async def test_rpc_session_runtime_fails_pending_call_when_process_exits(tmp_path):
    script = tmp_path / "exit_rpc.py"
    script.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    runtime = CliRpcSessionRuntime()

    with pytest.raises(RuntimeError, match="未返回响应"):
        async for _chunk in runtime.stream_turn(
            config=CliRpcSessionConfig(
                session_id="session-rpc-exit",
                agent_id="agent-rpc-exit",
                executable=sys.executable,
                args=[str(script)],
                env_vars={},
                cwd=str(tmp_path),
                protocol="mcp",
                cli_tool="codex",
            ),
            request=_codex_rpc_turn_request("hello"),
            silence_timeout_seconds=5,
        ):
            pass

    assert runtime.active_snapshots("session-rpc-exit") == []


def _codex_rpc_turn_request(prompt: str) -> CliRpcTurnRequest:
    return CliRpcTurnRequest(
        method="tools/call",
        params={
            "name": "codex",
            "arguments": {"prompt": prompt},
        },
        resume_method="tools/call",
        resume_params={
            "name": "codex-reply",
            "arguments": {"prompt": prompt},
        },
        native_session_param="arguments.threadId",
    )


def _opencode_rpc_turn_request(prompt: str) -> CliRpcTurnRequest:
    return CliRpcTurnRequest(
        method="session/prompt",
        params={
            "prompt": [{"type": "text", "text": prompt}],
        },
        native_session_param="sessionId",
    )


def _write_fake_codex_mcp_server(tmp_path: Path) -> Path:
    script = tmp_path / "fake_codex_mcp.py"
    script.write_text(
        "import json, sys, time\n"
        "thread_id = 'thread-1'\n"
        "def read_message():\n"
        "    first = sys.stdin.buffer.readline()\n"
        "    if not first:\n"
        "        return None\n"
        "    if first.lstrip().startswith(b'{'):\n"
        "        return json.loads(first.decode('utf-8'))\n"
        "    headers = {}\n"
        "    line = first\n"
        "    while line not in (b'\\r\\n', b'\\n', b''):\n"
        "        text = line.decode('ascii', errors='replace').strip()\n"
        "        if ':' in text:\n"
        "            key, value = text.split(':', 1)\n"
        "            headers[key.strip().lower()] = value.strip()\n"
        "        line = sys.stdin.buffer.readline()\n"
        "    length = int(headers.get('content-length') or '0')\n"
        "    if length <= 0:\n"
        "        raise RuntimeError('missing content length')\n"
        "    return json.loads(sys.stdin.buffer.read(length).decode('utf-8'))\n"
        "def write_message(message):\n"
        "    raw = json.dumps(message, ensure_ascii=False).encode('utf-8')\n"
        "    sys.stdout.buffer.write(f'Content-Length: {len(raw)}\\r\\n\\r\\n'.encode('ascii') + raw)\n"
        "    sys.stdout.buffer.flush()\n"
        "while True:\n"
        "    message = read_message()\n"
        "    if message is None:\n"
        "        break\n"
        "    if 'id' not in message:\n"
        "        continue\n"
        "    method = message.get('method')\n"
        "    if method == 'initialize':\n"
        "        write_message({'jsonrpc': '2.0', 'id': message['id'], 'result': {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'fake-codex', 'version': '1'}}})\n"
        "        continue\n"
        "    if method == 'tools/call':\n"
        "        params = message.get('params') or {}\n"
        "        name = params.get('name') or 'codex'\n"
        "        args = params.get('arguments') or {}\n"
        "        prompt = args.get('prompt') or ''\n"
        "        if str(prompt).startswith('slow'):\n"
        "            time.sleep(0.16)\n"
        "        current_thread = args.get('threadId') or thread_id\n"
        "        content = f'mcp:{name}:{prompt}:thread={current_thread}'\n"
        "        write_message({'jsonrpc': '2.0', 'id': message['id'], 'result': {'structuredContent': {'threadId': current_thread, 'content': content}, 'content': [{'type': 'text', 'text': content}]}})\n"
        "        continue\n"
        "    write_message({'jsonrpc': '2.0', 'id': message['id'], 'result': {}})\n",
        encoding="utf-8",
    )
    return script


def _write_fake_opencode_acp_server(tmp_path: Path) -> Path:
    script = tmp_path / "fake_opencode_acp.py"
    script.write_text(
        "import json, sys\n"
        "session_id = 'ses_1'\n"
        "def write_message(message):\n"
        "    sys.stdout.write(json.dumps(message, ensure_ascii=False) + '\\n')\n"
        "    sys.stdout.flush()\n"
        "def prompt_text(prompt):\n"
        "    if isinstance(prompt, str):\n"
        "        return prompt\n"
        "    if isinstance(prompt, list):\n"
        "        return ''.join(item.get('text', '') if isinstance(item, dict) else str(item) for item in prompt)\n"
        "    return ''\n"
        "for line in sys.stdin:\n"
        "    if not line.strip():\n"
        "        continue\n"
        "    message = json.loads(line)\n"
        "    if 'id' not in message:\n"
        "        continue\n"
        "    method = message.get('method')\n"
        "    if method == 'initialize':\n"
        "        write_message({'jsonrpc': '2.0', 'id': message['id'], 'result': {'protocolVersion': 1, 'serverCapabilities': {}}})\n"
        "        continue\n"
        "    if method == 'session/new':\n"
        "        write_message({'jsonrpc': '2.0', 'id': message['id'], 'result': {'sessionId': session_id}})\n"
        "        continue\n"
        "    if method == 'session/prompt':\n"
        "        params = message.get('params') or {}\n"
        "        text = prompt_text(params.get('prompt'))\n"
        "        sid = params.get('sessionId') or session_id\n"
        "        write_message({'jsonrpc': '2.0', 'method': 'session/update', 'params': {'sessionId': sid, 'update': {'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': f'acp:{sid}:{text}'}}}})\n"
        "        write_message({'jsonrpc': '2.0', 'id': message['id'], 'result': {'stopReason': 'end_turn'}})\n"
        "        continue\n"
        "    write_message({'jsonrpc': '2.0', 'id': message['id'], 'result': {}})\n",
        encoding="utf-8",
    )
    return script
