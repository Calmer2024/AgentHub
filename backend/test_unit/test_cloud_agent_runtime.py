from types import SimpleNamespace

from app.services.cloud_agent_runtime import _cloud_persistent_process_supported


class FakeCliAgents:
    def supports_persistent_process(self, agent) -> bool:
        return bool(getattr(agent, "supports_persistent", False))


def test_local_dev_cloud_runtime_uses_adapter_persistent_policy():
    agent = SimpleNamespace(
        cli_tool="codex",
        prepared_invocation=False,
        supports_persistent=True,
    )

    assert _cloud_persistent_process_supported(
        agent,
        {"provider": "local_dev"},
        FakeCliAgents(),
    ) is True


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


def test_docker_cloud_runtime_enables_codex_mcp_wrapper():
    agent = SimpleNamespace(
        cli_tool="codex",
        prepared_invocation=True,
        supports_persistent=True,
    )

    assert _cloud_persistent_process_supported(
        agent,
        {"provider": "docker"},
        FakeCliAgents(),
    ) is True


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
