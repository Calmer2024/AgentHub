import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.api.agents import AgentConfigRead
from app.config import settings
from app.models import AgentConfig, RuntimeRun, Sandbox, WorkspaceVolume
from app.services.runner_provider import DockerRunnerProvider, SshDockerRunnerProvider


OWNER = {
    "X-AgentHub-User-Email": "phase15-owner@example.com",
    "X-AgentHub-User-Name": "Phase15 Owner",
}


def _events(text: str) -> list[dict]:
    items: list[dict] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if block.startswith("data: "):
            items.append(json.loads(block[6:]))
    return items


def _phase15_cli() -> Path:
    script = Path(__file__).resolve().parents[1] / ".test-bin" / "phase15_runner_cli.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "import os, sys\n"
        "data = os.read(sys.stdin.fileno(), 65536).decode('utf-8', errors='replace')\n"
        "with open('phase15-output.txt', 'w', encoding='utf-8') as f:\n"
        "    f.write('runner synced')\n"
        "sys.stdout.write('phase15 cloud ok')\n",
        encoding="utf-8",
    )
    return script


async def _create_cloud_session(test_client) -> tuple[dict, dict, dict]:
    agent = await test_client.post(
        "/api/agents",
        json={
            "name": "Phase15 Runner Fixture Agent",
            "description": "Phase 15 fixture",
            "cliTool": "custom",
            "executable": sys.executable,
            "initArgs": [str(_phase15_cli())],
        },
    )
    assert agent.status_code == 201, agent.text
    project = await test_client.post(
        "/api/projects",
        json={"name": "Phase15 Cloud Runtime", "workspaceMode": "cloud"},
        headers=OWNER,
    )
    assert project.status_code == 201, project.text
    session = await test_client.post(
        "/api/sessions",
        json={
            "title": "Phase15 云端会话",
            "projectId": project.json()["id"],
            "agentConfigId": agent.json()["id"],
        },
        headers=OWNER,
    )
    assert session.status_code == 201, session.text
    return agent.json(), project.json(), session.json()


@pytest.mark.asyncio
async def test_runtime_images_runner_nodes_and_sandbox_lifecycle(test_client, db_session):
    _agent, project, _session = await _create_cloud_session(test_client)

    images = await test_client.get("/api/runtime/images", headers=OWNER)
    assert images.status_code == 200, images.text
    assert images.json()["items"][0]["image"] == settings.agenthub_runtime_image
    assert images.json()["items"][0]["provider"] == "local_dev"

    nodes = await test_client.get("/api/runtime/runner-nodes", headers=OWNER)
    assert nodes.status_code == 200, nodes.text
    assert nodes.json()["items"][0]["provider"] == "local_dev"
    assert nodes.json()["items"][0]["status"] == "healthy"

    sandbox = await test_client.post(
        "/api/sandboxes",
        json={"workspaceId": project["workspaceId"]},
        headers=OWNER,
    )
    assert sandbox.status_code == 201, sandbox.text
    body = sandbox.json()
    assert body["provider"] == "local_dev"
    assert body["externalId"].startswith("local-dev-")
    assert body["region"] == settings.agenthub_runner_region
    assert body["status"] == "ready"

    volume = await db_session.execute(
        select(WorkspaceVolume).where(WorkspaceVolume.workspace_id == project["workspaceId"])
    )
    assert volume.scalars().first().storage_provider == "local_dev"

    stopped = await test_client.post(
        f"/api/sandboxes/{body['id']}/stop",
        json={"reason": "phase15 lifecycle test"},
        headers=OWNER,
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["status"] == "disposed"

    disposed = await test_client.get(f"/api/sandboxes/{body['id']}", headers=OWNER)
    assert disposed.status_code == 200, disposed.text
    assert disposed.json()["disposedAt"]


@pytest.mark.asyncio
async def test_cloud_run_records_sync_and_disposes_sandbox(test_client, db_session):
    _agent, project, session = await _create_cloud_session(test_client)

    response = await test_client.post(
        f"/api/sessions/{session['id']}/chat",
        json={"content": "请在 runner 中执行并同步文件"},
        headers=OWNER,
    )
    assert response.status_code == 200, response.text
    events = _events(response.text)
    types = [event.get("type") for event in events]
    assert "workspace.sync.started" in types
    assert "workspace.sync.completed" in types
    assert "sandbox.disposed" in types

    run_started = next(event for event in events if event.get("type") == "run.started")
    run_id = run_started["runId"]
    sandbox_id = run_started["run"]["metadata"]["sandboxId"]
    runtime_run = await db_session.get(RuntimeRun, run_id)
    assert runtime_run.status == "completed"
    assert runtime_run.queued_at is not None
    assert runtime_run.sync_completed_at is not None

    sandbox = await db_session.get(Sandbox, sandbox_id)
    assert sandbox.provider == "local_dev"
    assert sandbox.status == "disposed"
    assert sandbox.disposed_at is not None

    volume = await db_session.execute(
        select(WorkspaceVolume).where(WorkspaceVolume.workspace_id == project["workspaceId"])
    )
    assert volume.scalars().first().last_synced_at is not None


@pytest.mark.asyncio
async def test_cloud_regenerate_reuses_runtime_and_replaces_assistant_message(test_client):
    _agent, _project, session = await _create_cloud_session(test_client)

    response = await test_client.post(
        f"/api/sessions/{session['id']}/chat",
        json={"content": "首次云端运行"},
        headers=OWNER,
    )
    assert response.status_code == 200, response.text

    messages = await test_client.get(f"/api/sessions/{session['id']}/messages", headers=OWNER)
    assert messages.status_code == 200, messages.text
    assistant = [item for item in messages.json() if item["role"] == "assistant"][-1]

    regenerate = await test_client.post(f"/api/messages/{assistant['id']}/regenerate", headers=OWNER)
    assert regenerate.status_code == 200, regenerate.text
    events = _events(regenerate.text)
    assert any(event.get("type") == "run.started" for event in events)
    done = [event for event in events if event.get("done")][-1]
    assert done["messageId"] == assistant["id"]
    assert done.get("error") is None

    refreshed = await test_client.get(f"/api/messages/{assistant['id']}", headers=OWNER)
    assert refreshed.status_code == 200, refreshed.text
    body = refreshed.json()
    assert body["content"] == "phase15 cloud ok"
    assert body["metadata"]["runStatus"] == "running"
    assert body["metadata"]["versions"][-1]["reason"] == "regenerate"
    assert body["metadata"]["cloudRuntime"]["provider"] == "local_dev"


@pytest.mark.asyncio
async def test_cloud_group_chat_mentions_run_only_named_members(test_client):
    scripts = [
        "import os, sys; os.read(sys.stdin.fileno(), 65536); print('GROUP_AGENT_ONE_OK')",
        "import os, sys; os.read(sys.stdin.fileno(), 65536); print('GROUP_AGENT_TWO_OK')",
    ]
    agents = []
    for index, script in enumerate(scripts, start=1):
        response = await test_client.post(
            "/api/agents",
            json={
                "name": f"Cloud Group Fixture {index}",
                "description": "Phase 15 group fixture",
                "cliTool": "custom",
                "executable": sys.executable,
                "initArgs": ["-c", script],
            },
        )
        assert response.status_code == 201, response.text
        agents.append(response.json())
    project = await test_client.post(
        "/api/projects",
        json={"name": "Phase15 Cloud Group", "workspaceMode": "cloud"},
        headers=OWNER,
    )
    assert project.status_code == 201, project.text
    session = await test_client.post(
        "/api/sessions",
        json={
            "title": "Phase15 云端群聊",
            "projectId": project.json()["id"],
            "mode": "group",
            "agentConfigIds": [agent["id"] for agent in agents],
        },
        headers=OWNER,
    )
    assert session.status_code == 201, session.text

    response = await test_client.post(
        f"/api/sessions/{session.json()['id']}/chat",
        json={
            "content": "请两个 Agent 都执行",
            "mentions": [agent["id"] for agent in agents],
        },
        headers=OWNER,
    )
    assert response.status_code == 200, response.text
    events = _events(response.text)
    assert any(event.get("type") == "orchestrator.route" for event in events)
    assert "GROUP_AGENT_ONE_OK" in response.text
    assert "GROUP_AGENT_TWO_OK" in response.text
    assert [event.get("done") for event in events].count(True) == 1

    messages = await test_client.get(f"/api/sessions/{session.json()['id']}/messages", headers=OWNER)
    assert messages.status_code == 200, messages.text
    assistant_contents = [item["content"] for item in messages.json() if item["role"] == "assistant"]
    assert any("GROUP_AGENT_ONE_OK" in content for content in assistant_contents)
    assert any("GROUP_AGENT_TWO_OK" in content for content in assistant_contents)


@pytest.mark.asyncio
async def test_cloud_group_chat_mentions_orchestrator_runs_planner_not_fallback(test_client):
    product = await test_client.post(
        "/api/agents",
        json={
            "name": "云端产品经理",
            "description": "产品范围和验收标准",
            "cliTool": "custom",
            "executable": sys.executable,
            "initArgs": ["-c", "import os, sys; os.read(sys.stdin.fileno(), 65536); print('PRODUCT_SHOULD_NOT_RUN')"],
            "primarySkill": "product_manager",
        },
    )
    assert product.status_code == 201, product.text
    plan_payload = {
        "plan_id": "cloud_plan_mention_orchestrator",
        "tasks": [{
            "task_id": "T1",
            "title": "需求澄清",
            "goal": "先对齐预约单页范围",
            "required_skills": ["product_manager"],
            "assigned_agent_id": product.json()["id"],
            "assigned_agent_name": "云端产品经理",
            "depends_on": [],
        }],
    }
    orchestrator = await test_client.post(
        "/api/agents",
        json={
            "name": "云端 Orchestrator 调度器",
            "description": "云端计划调度器",
            "cliTool": "custom",
            "executable": sys.executable,
            "initArgs": ["-c", f"import os, sys; os.read(sys.stdin.fileno(), 65536); sys.stdout.buffer.write({json.dumps(json.dumps(plan_payload, ensure_ascii=False))}.encode('utf-8'))"],
            "primarySkill": "orchestrator_planner",
            "contextPolicy": "planning_only",
        },
    )
    assert orchestrator.status_code == 201, orchestrator.text
    project = await test_client.post(
        "/api/projects",
        json={"name": "Phase15 Cloud Orchestrator Mention", "workspaceMode": "cloud"},
        headers=OWNER,
    )
    assert project.status_code == 201, project.text
    session = await test_client.post(
        "/api/sessions",
        json={
            "title": "Phase15 云端调度器群聊",
            "projectId": project.json()["id"],
            "mode": "group",
            "agentConfigIds": [product.json()["id"], orchestrator.json()["id"]],
        },
        headers=OWNER,
    )
    assert session.status_code == 201, session.text

    response = await test_client.post(
        f"/api/sessions/{session.json()['id']}/chat",
        json={
            "content": "@云端 Orchestrator 调度器 先做预约单页计划",
            "mentions": [orchestrator.json()["id"]],
        },
        headers=OWNER,
    )
    assert response.status_code == 200, response.text
    events = _events(response.text)
    event_types = [event.get("type") for event in events]
    assert "agent.start" in event_types
    assert "orchestrator.route" not in event_types
    assert "orchestrator.task_started" not in event_types
    assert "PRODUCT_SHOULD_NOT_RUN" not in response.text
    assert [event.get("done") for event in events].count(True) == 1

    messages = await test_client.get(f"/api/sessions/{session.json()['id']}/messages", headers=OWNER)
    assert messages.status_code == 200, messages.text
    assistants = [item for item in messages.json() if item["role"] == "assistant"]
    assert assistants[-1]["agentName"] == "云端 Orchestrator 调度器"
    assert assistants[-1]["metadata"]["orchestratorPlan"]["ok"] is True
    assert assistants[-1]["metadata"]["orchestratorPlan"]["normalizedPlan"]["tasks"][0]["title"] == "需求澄清"


@pytest.mark.asyncio
async def test_cloud_group_chat_without_mentions_uses_steward_then_plan_first(test_client):
    roles = [
        ("云端产品经理", "product_manager", "PRODUCT_SHOULD_NOT_RUN"),
        ("云端 UI 设计师", "ux_ui_designer", "DESIGNER_SHOULD_NOT_RUN"),
        ("云端前端工程师", "frontend_engineer", "FRONTEND_SHOULD_NOT_RUN"),
    ]
    agents = []
    for name, primary_skill, marker in roles:
        response = await test_client.post(
            "/api/agents",
            json={
                "name": name,
                "description": name,
                "cliTool": "custom",
                "executable": sys.executable,
                "initArgs": ["-c", f"import os, sys; os.read(sys.stdin.fileno(), 65536); print({json.dumps(marker)})"],
                "primarySkill": primary_skill,
            },
        )
        assert response.status_code == 201, response.text
        agents.append(response.json())
    steward_payload = {
        "route_type": "mini_collab",
        "reply": "我先生成一份小型协作计划，再按产品、设计、前端推进。",
        "reason": "用户明确要求先产品经理、再 UI、再前端。",
        "selected_agent_ids": [agent["id"] for agent in agents],
        "task_brief": "宠物洗护店单页预约介绍页面",
        "confidence": 0.93,
        "requires_approval": True,
        "risk_level": "medium",
    }
    plan_payload = {
        "plan_id": "cloud_pet_booking_page",
        "tasks": [
            {
                "task_id": "T1",
                "title": "产品范围对齐",
                "goal": "明确服务、价格、预约须知和表单字段",
                "required_skills": ["product_manager"],
                "assigned_agent_id": agents[0]["id"],
                "assigned_agent_name": agents[0]["name"],
                "depends_on": [],
            },
            {
                "task_id": "T2",
                "title": "页面体验设计",
                "goal": "输出单页信息架构和视觉方向",
                "required_skills": ["ux_ui_designer"],
                "assigned_agent_id": agents[1]["id"],
                "assigned_agent_name": agents[1]["name"],
                "depends_on": ["T1"],
            },
            {
                "task_id": "T3",
                "title": "静态页面实现",
                "goal": "实现静态 HTML 预约介绍页",
                "required_skills": ["frontend_engineer"],
                "assigned_agent_id": agents[2]["id"],
                "assigned_agent_name": agents[2]["name"],
                "depends_on": ["T2"],
            },
        ],
    }
    steward_json = json.dumps(steward_payload, ensure_ascii=False)
    plan_json = json.dumps(plan_payload, ensure_ascii=False)
    orchestrator_script = (
        "import os, sys\n"
        "data = os.read(sys.stdin.fileno(), 65536).decode('utf-8', errors='replace')\n"
        f"steward = {json.dumps(steward_json)}\n"
        f"plan = {json.dumps(plan_json)}\n"
        "sys.stdout.buffer.write((plan if 'route_type=mini_collab' in data else steward).encode('utf-8'))\n"
    )
    orchestrator = await test_client.post(
        "/api/agents",
        json={
            "name": "云端 Orchestrator 调度器",
            "description": "云端计划调度器",
            "cliTool": "custom",
            "executable": sys.executable,
            "initArgs": ["-c", orchestrator_script],
            "primarySkill": "orchestrator_planner",
            "contextPolicy": "planning_only",
        },
    )
    assert orchestrator.status_code == 201, orchestrator.text
    project = await test_client.post(
        "/api/projects",
        json={"name": "Phase15 Cloud Steward", "workspaceMode": "cloud"},
        headers=OWNER,
    )
    assert project.status_code == 201, project.text
    session = await test_client.post(
        "/api/sessions",
        json={
            "title": "Phase15 云端管家群聊",
            "projectId": project.json()["id"],
            "mode": "group",
            "agentConfigIds": [agent["id"] for agent in agents] + [orchestrator.json()["id"]],
        },
        headers=OWNER,
    )
    assert session.status_code == 201, session.text

    response = await test_client.post(
        f"/api/sessions/{session.json()['id']}/chat",
        json={"content": "我经营一家小型宠物洗护店，先和产品经理对齐一下，然后还要UI设计师，然后做前端"},
        headers=OWNER,
    )
    assert response.status_code == 200, response.text
    events = _events(response.text)
    event_types = [event.get("type") for event in events]
    agent_starts = [event.get("agentName") for event in events if event.get("type") == "agent.start"]
    assert "orchestrator.steward_decision" in event_types
    assert "orchestrator.route" not in event_types
    assert "orchestrator.task_started" not in event_types
    assert agent_starts == ["云端 Orchestrator 调度器", "云端 Orchestrator 调度器"]
    assert "PRODUCT_SHOULD_NOT_RUN" not in response.text
    assert "DESIGNER_SHOULD_NOT_RUN" not in response.text
    assert "FRONTEND_SHOULD_NOT_RUN" not in response.text
    assert [event.get("done") for event in events].count(True) == 1

    messages = await test_client.get(f"/api/sessions/{session.json()['id']}/messages", headers=OWNER)
    assert messages.status_code == 200, messages.text
    assistants = [item for item in messages.json() if item["role"] == "assistant"]
    assert assistants[0]["metadata"]["stewardDecision"]["routeType"] == "mini_collab"
    assert assistants[0]["content"] == "我先生成一份小型协作计划，再按产品、设计、前端推进。"
    assert assistants[1]["metadata"]["orchestratorPlan"]["ok"] is True
    plan = assistants[1]["metadata"]["orchestratorPlan"]["normalizedPlan"]
    assert [task["assigned_agent_name"] for task in plan["tasks"]] == [
        "云端产品经理",
        "云端 UI 设计师",
        "云端前端工程师",
    ]


@pytest.mark.asyncio
async def test_docker_runner_wraps_cli_with_limits_and_secret_env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "agenthub_runtime_image", "python:3.12-slim")
    monkeypatch.setattr(settings, "agenthub_runner_cpu", 0.5)
    monkeypatch.setattr(settings, "agenthub_runner_network_policy", "none")
    sandbox = Sandbox(
        id="sandbox-phase15-abcdef",
        workspace_id="workspace-1",
        image="python:3.12-slim",
        resource_limits_json=json.dumps({"memoryMb": 256, "diskMb": 512, "runtimeSeconds": 30}),
    )
    agent = SimpleNamespace(
        id="agent-1",
        name="Docker Fixture",
        cli_tool="claude_code",
        executable="claude",
        init_args=json.dumps(["-p"], ensure_ascii=False),
        env_vars=json.dumps({"PHASE15_TOKEN": "super-secret"}, ensure_ascii=False),
    )

    spec = await DockerRunnerProvider().prepare_process(
        sandbox=sandbox,
        agent=agent,
        run_id="run-phase15-abcdef",
        workspace_path=str(tmp_path),
    )

    args = json.loads(spec.agent.init_args)
    env = json.loads(spec.agent.env_vars)
    assert spec.agent.cli_tool == "claude_code"
    assert spec.agent.executable == settings.agenthub_runner_docker_binary
    assert spec.agent.close_stdin_after_prompt is True
    assert spec.agent.prepared_invocation is True
    assert args[:3] == ["run", "--rm", "-i"]
    assert args[args.index("--network") + 1] == "none"
    assert args[args.index("--memory") + 1] == "256m"
    assert args[args.index("--cpus") + 1] == "0.5"
    assert args[args.index("--workdir") + 1] == "/workspace"
    assert args[-3:] == ["python:3.12-slim", "claude", "-p"]
    assert "--env-file" in args
    env_file = Path(args[args.index("--env-file") + 1])
    try:
        assert env_file.exists()
        assert "PHASE15_TOKEN=super-secret" in env_file.read_text(encoding="utf-8")
        assert "PHASE15_TOKEN" not in args
        assert "super-secret" not in json.dumps(args, ensure_ascii=False)
        assert "PHASE15_TOKEN" not in env
        assert spec.metadata["provider"] == "docker"
        assert spec.metadata["resourceLimits"]["memoryMb"] == 256
    finally:
        env_file.unlink(missing_ok=True)


def test_saas_agent_status_uses_cloud_runtime_image(monkeypatch):
    monkeypatch.setattr(settings, "agenthub_edition", "saas")
    monkeypatch.setattr(settings, "agenthub_auth_required", True)
    monkeypatch.setattr(settings, "agenthub_runner_provider", "docker")
    monkeypatch.setattr(settings, "agenthub_runtime_image", "agenthub/codex-claude-opencode-runtime:phase15")
    monkeypatch.setattr(settings, "agenthub_runtime_images", "")
    agent = AgentConfig(
        id="agent-codex-runtime",
        name="Codex",
        description="云端 Codex",
        system_prompt="",
        rules="",
        agent_type="cli_wrapper",
        cli_tool="codex",
        executable="codex",
        init_args="[]",
        env_vars="{}",
        primary_skill="general_coding",
        auxiliary_skills="[]",
        toolset="[]",
        context_policy="workspace_coding",
        avatar="",
        is_active=True,
    )

    data = AgentConfigRead.from_model(agent).model_dump(by_alias=True)

    assert data["status"] == "ready"
    assert data["version"] == "codex 由云端 Runtime Image 提供"
    assert data["executablePath"] is None


@pytest.mark.asyncio
async def test_ssh_docker_runner_keeps_password_and_secrets_out_of_argv(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "agenthub_runner_ssh_host", "203.0.113.10")
    monkeypatch.setattr(settings, "agenthub_runner_ssh_user", "root")
    monkeypatch.setattr(settings, "agenthub_runner_ssh_password", "remote-password")
    monkeypatch.setattr(settings, "agenthub_runner_ssh_workspace_root", "/tmp/agenthub/workspaces")
    sandbox = Sandbox(
        id="sandbox-ssh-phase15",
        workspace_id="workspace-ssh-1",
        image="python:3.12-slim",
        resource_limits_json=json.dumps({"memoryMb": 256, "diskMb": 512, "runtimeSeconds": 30}),
    )
    agent = SimpleNamespace(
        id="agent-ssh-1",
        name="SSH Docker Fixture",
        cli_tool="custom",
        executable=sys.executable,
        init_args=json.dumps(["-c", "print('ok')"], ensure_ascii=False),
        env_vars=json.dumps({"PHASE15_TOKEN": "super-secret"}, ensure_ascii=False),
    )

    spec = await SshDockerRunnerProvider().prepare_process(
        sandbox=sandbox,
        agent=agent,
        run_id="run-ssh-phase15",
        workspace_path=str(tmp_path),
    )

    args = json.loads(spec.agent.init_args)
    wrapper_env = json.loads(spec.agent.env_vars)
    config = json.loads(wrapper_env["AGENTHUB_SSH_DOCKER_CONFIG"])
    assert args == [str(Path(__file__).resolve().parents[1] / "app" / "services" / "ssh_docker_runner_entry.py")]
    assert spec.agent.close_stdin_after_prompt is True
    assert spec.agent.prepared_invocation is True
    assert "remote-password" not in json.dumps(args, ensure_ascii=False)
    assert "super-secret" not in json.dumps(args, ensure_ascii=False)
    assert "remote-password" not in json.dumps(spec.metadata, ensure_ascii=False)
    assert "super-secret" not in json.dumps(spec.metadata, ensure_ascii=False)
    assert config["password"] == "remote-password"
    assert config["envVars"]["PHASE15_TOKEN"] == "super-secret"
    assert "--env-file" in config["dockerArgs"]
    assert "super-secret" not in json.dumps(config["dockerArgs"], ensure_ascii=False)
    assert spec.metadata["remoteWorkspacePath"].startswith("cloud-volume://agenthub/ssh_docker/")
