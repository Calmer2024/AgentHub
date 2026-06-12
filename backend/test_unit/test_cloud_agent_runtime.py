from pathlib import Path
from types import SimpleNamespace

from app.services.cloud_agent_runtime import (
    _append_cloud_runtime_context,
    _cloud_failure_diagnostic,
    _cloud_persistent_process_supported,
)


class FakeCliAgents:
    def supports_persistent_process(self, agent) -> bool:
        return bool(getattr(agent, "supports_persistent", False))


def test_local_dev_cloud_runtime_uses_adapter_persistent_policy_for_non_codex():
    agent = SimpleNamespace(
        cli_tool="claude_code",
        prepared_invocation=False,
        supports_persistent=True,
    )

    assert _cloud_persistent_process_supported(
        agent,
        {"provider": "local_dev"},
        FakeCliAgents(),
    ) is True


def test_cloud_runtime_disables_codex_persistent_rpc_to_preserve_json_streaming():
    agent = SimpleNamespace(
        cli_tool="codex",
        prepared_invocation=False,
        supports_persistent=True,
    )

    assert _cloud_persistent_process_supported(
        agent,
        {"provider": "local_dev"},
        FakeCliAgents(),
    ) is False


def test_docker_cloud_runtime_keeps_opencode_persistent_wrapper_enabled():
    agent = SimpleNamespace(
        cli_tool="opencode",
        prepared_invocation=True,
        supports_persistent=True,
    )

    assert _cloud_persistent_process_supported(
        agent,
        {"provider": "ssh_docker"},
        FakeCliAgents(),
    ) is True


def test_docker_cloud_runtime_disables_codex_mcp_wrapper():
    agent = SimpleNamespace(
        cli_tool="codex",
        prepared_invocation=True,
        supports_persistent=True,
    )

    assert _cloud_persistent_process_supported(
        agent,
        {"provider": "docker"},
        FakeCliAgents(),
    ) is False


def test_ssh_docker_cloud_runtime_does_not_enable_codex_wrapper():
    agent = SimpleNamespace(
        cli_tool="codex",
        prepared_invocation=True,
        supports_persistent=True,
    )

    assert _cloud_persistent_process_supported(
        agent,
        {"provider": "ssh_docker"},
        FakeCliAgents(),
    ) is False


def test_docker_cloud_runtime_does_not_enable_unadapted_claude_wrapper():
    agent = SimpleNamespace(
        cli_tool="claude_code",
        prepared_invocation=True,
        supports_persistent=True,
    )

    assert _cloud_persistent_process_supported(
        agent,
        {"provider": "docker"},
        FakeCliAgents(),
    ) is False


def test_cloud_runtime_respects_adapter_without_persistent_support():
    agent = SimpleNamespace(
        cli_tool="opencode",
        prepared_invocation=True,
        supports_persistent=False,
    )

    assert _cloud_persistent_process_supported(
        agent,
        {"provider": "local_dev"},
        FakeCliAgents(),
    ) is False


def test_runtime_image_dockerfile_preinstalls_document_toolchain():
    dockerfile = (Path(__file__).resolve().parents[2] / "deploy" / "runtime" / "Dockerfile").read_text(
        encoding="utf-8",
    )

    assert "AGENTHUB_RUNTIME_BASE_IMAGE" in dockerfile
    assert "python3-docx" in dockerfile
    assert "python3-venv" in dockerfile
    assert "pandoc" in dockerfile
    assert "libreoffice-writer" in dockerfile
    assert "PIP_NO_INPUT=1" in dockerfile
    assert "repo.huaweicloud.com/repository/pypi/simple" in dockerfile


def test_cloud_failure_diagnostic_explains_docx_dependency_timeout(monkeypatch):
    monkeypatch.setattr("app.services.cloud_agent_runtime.time.monotonic", lambda: 1000.0)
    diagnostic = _cloud_failure_diagnostic(
        exit_code=143,
        start_time=405.0,
        runtime_limit=600,
        raw_output=(
            "python3 -c \"import docx\"\n"
            "ModuleNotFoundError: No module named 'docx'\n"
            "pip install python-docx --break-system-packages\n"
            "note: See PEP 668 for the detailed specification.\n"
        ),
    )

    assert diagnostic.runtime_status == "timed_out"
    assert "python-docx / venv" in diagnostic.message
    assert "Runtime Image" in diagnostic.message


def test_cloud_runtime_context_guides_document_generation_without_live_installs():
    prompt = _append_cloud_runtime_context("你是文档 Agent")

    assert "python-docx" in prompt
    assert "不要为了常见文档格式" in prompt
    assert prompt == _append_cloud_runtime_context(prompt)
