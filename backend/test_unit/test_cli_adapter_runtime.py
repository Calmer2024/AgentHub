import asyncio
import sys
from pathlib import Path

import pytest

from app.agents.cli_adapters import ClaudeCodeAdapter, CliAgentAdapter, CodexAdapter, OpenCodeAdapter
from app.agents.cli_output_parser import CliOutputParser
from app.agents.cli_runtime import CliProcessManager, PromptInterceptor, StreamSanitizer, cli_process_manager
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


def test_codex_proxy_settings_add_v1_to_gateway_origin():
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
    assert 'model_providers.agenthub_proxy.base_url="https://proxy.example.com/v1"' in joined


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

    joined = "\n".join(args)
    assert "--ignore-user-config" in args
    assert 'model="gpt-5.5"' in joined
    assert 'model_providers.agenthub_proxy.name="Local Proxy"' in joined
    assert 'model_providers.agenthub_proxy.base_url="https://proxy.example.com/v1"' in joined
    assert 'model_providers.agenthub_proxy.env_key="AGENTHUB_CODEX_PROVIDER_TOKEN"' in joined
    assert env == {"AGENTHUB_CODEX_PROVIDER_TOKEN": "proxy-key"}


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

    joined = "\n".join(args)
    assert "--ignore-user-config" in args
    assert 'model_providers.agenthub_proxy.base_url="https://proxy.example.com/v1"' in joined
    assert 'model_providers.agenthub_proxy.env_key="AGENTHUB_CODEX_PROVIDER_TOKEN"' in joined
    assert env == {"AGENTHUB_CODEX_PROVIDER_TOKEN": "proxy-key"}


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

    joined = "\n".join(args)
    assert "--ignore-user-config" in args
    assert 'model_providers.agenthub_proxy.base_url="https://api.openai.com/v1"' in joined
    assert "requires_openai_auth=true" in joined
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
