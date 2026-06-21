"""Chat SSE 流式 API 测试 + SSE JSON 合法性回归测试。"""
import json
import sys
import uuid
from types import SimpleNamespace
from pathlib import Path
import pytest

from app.models import AgentConfig, EngineSession, Project
from app.agents.cli_events import CliEvent
from app.agents.cli_trace import process_completed_trace


BACKEND_ROOT = Path(__file__).resolve().parents[3] / "backend"


@pytest.mark.asyncio
class TestChatStream:
    async def test_sse_returns_200(self, test_client, test_session):
        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Hello"},
        )
        assert resp.status_code == 200

    async def test_sse_events_are_valid_json(self, test_client, test_session):
        """回归测试：修复 {token!r} 导致的 SSE 单引号 JSON 问题。"""
        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Hello"},
        )
        lines = [line async for line in resp.aiter_lines()]
        for line in lines:
            if line.startswith("data: "):
                data = json.loads(line[6:])
                assert "done" in data
                if "token" in data:
                    assert isinstance(data["token"], str)

    async def test_sse_stream_collects_all_tokens(self, test_client, test_session):
        """验证流式输出收集了全部 token。"""
        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Hello"},
        )
        full_content = ""
        got_done = False
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if data["token"]:
                    full_content += data["token"]
                if data["done"]:
                    got_done = True
        assert got_done
        assert full_content == "Hello, World!"

    async def test_sse_final_event_has_message_id(self, test_client, test_session):
        """验证最后的 done 事件包含 message_id。"""
        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Hello"},
        )
        last_data = None
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                last_data = json.loads(line[6:])
        assert last_data["done"] is True
        assert "messageId" in last_data
        assert last_data["messageId"] is not None

    async def test_execution_trace_streamed(self, test_client, test_session):
        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Hello"},
        )
        trace_events = []
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            if data.get("type") == "agent.trace.delta":
                trace_events.append(data)

        assert trace_events
        assert any(event["item"]["kind"] == "process" for event in trace_events)


@pytest.mark.asyncio
class TestChatErrors:
    async def test_empty_content(self, test_client, test_session):
        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": ""},
        )
        assert resp.status_code == 400

    async def test_whitespace_only_content(self, test_client, test_session):
        resp = await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "   "},
        )
        assert resp.status_code == 400

    async def test_nonexistent_session(self, test_client):
        resp = await test_client.post(
            "/api/sessions/nonexistent-id/chat",
            json={"content": "Hello"},
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestChatPersistence:
    async def test_messages_persisted_after_chat(self, test_client, test_session):
        """验证聊天完成后 user + assistant 消息都已持久化。"""
        await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Hello"},
        )
        resp = await test_client.get(f"/api/sessions/{test_session}/messages")
        assert resp.status_code == 200
        messages = resp.json()
        assert len(messages) == 2
        roles = [m["role"] for m in messages]
        assert "user" in roles
        assert "assistant" in roles

    async def test_execution_trace_persisted_after_chat(self, test_client, test_session):
        await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Hello"},
        )
        resp = await test_client.get(f"/api/sessions/{test_session}/messages")
        assistant = [m for m in resp.json() if m["role"] == "assistant"][0]
        trace = assistant["metadata"]["executionTrace"]

        assert trace["status"] == "completed"
        assert trace["items"]
        assert trace["items"][0]["kind"] == "process"

    async def test_orchestrator_single_chat_persists_structured_plan(self, test_client, db_session, monkeypatch):
        async def fake_stream(self, **kwargs):
            yield CliEvent(
                "agent.output",
                "proc-1",
                chunk=json.dumps({
                    "plan_id": "plan_test",
                    "status": "draft",
                    "tasks": [{
                        "task_id": "T1",
                        "title": "需求澄清",
                        "goal": "明确员工报销业务边界",
                        "required_skills": ["requirements_analyst"],
                        "depends_on": [],
                    }],
                }, ensure_ascii=False),
                chunk_type="text",
            )
            yield CliEvent("agent.process.completed", "proc-1", exit_code=0)

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        project = Project(
            id=str(uuid.uuid4()),
            name="测试项目",
            workspace_path=str(BACKEND_ROOT / ".test-workspaces" / str(uuid.uuid4())),
            status="ready",
        )
        Path(project.workspace_path).mkdir(parents=True, exist_ok=True)
        db_session.add(project)
        await db_session.commit()

        agent_res = await test_client.post("/api/agents", json={
            "name": "Orchestrator 调度器",
            "description": "测试调度器",
            "cliTool": "custom",
            "executable": sys.executable,
            "initArgs": [],
            "primarySkill": "orchestrator_planner",
            "auxiliarySkills": [],
            "contextPolicy": "planning_only",
        })
        assert agent_res.status_code == 201
        agent_id = agent_res.json()["id"]

        session_res = await test_client.post("/api/sessions", json={
            "title": "调度器单聊",
            "projectId": project.id,
            "agentConfigId": agent_id,
        })
        assert session_res.status_code == 201
        session_id = session_res.json()["id"]

        await test_client.post(f"/api/sessions/{session_id}/chat", json={"content": "生成 draft plan"})
        resp = await test_client.get(f"/api/sessions/{session_id}/messages")
        assistant = [message for message in resp.json() if message["role"] == "assistant"][0]

        assert "orchestratorPlan" in assistant["metadata"], assistant
        assert assistant["metadata"]["orchestratorPlan"]["ok"] is True
        assert assistant["metadata"]["orchestratorPlan"]["normalizedPlan"]["tasks"][0]["title"] == "需求澄清"
        assert "mermaid" in assistant["metadata"]["orchestratorPlan"]["visualization"]

    async def test_single_chat_generates_title_for_default_agent_title(
        self, test_client, test_agent, monkeypatch,
    ):
        class FakeSystemLLM:
            def is_configured(self):
                return True

            async def chat(self, **kwargs):
                return SimpleNamespace(content="登录页优化")

        from app.services import session_title_service
        monkeypatch.setattr(session_title_service, "system_llm", FakeSystemLLM())

        session_res = await test_client.post("/api/sessions", json={
            "title": test_agent.name,
            "agentConfigId": test_agent.id,
        })
        session_id = session_res.json()["id"]

        resp = await test_client.post(
            f"/api/sessions/{session_id}/chat",
            json={"content": "帮我优化登录页交互"},
        )
        events = []
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        assert any(event.get("type") == "session.title_updated" for event in events)
        session = (await test_client.get(f"/api/sessions/{session_id}")).json()
        assert session["title"] == "登录页优化"

    async def test_single_chat_generates_title_after_persistent_turn_completed(
        self, test_client, test_agent, monkeypatch,
    ):
        class FakeSystemLLM:
            def is_configured(self):
                return True

            async def chat(self, **kwargs):
                return SimpleNamespace(content="常驻进程续聊")

        async def fake_stream(self, **kwargs):
            yield CliEvent(
                "agent.output",
                "proc-persistent",
                chunk="turn done",
                chunk_type="text",
            )
            yield CliEvent("agent.process.turn_completed", "proc-persistent", exit_code=0)

        from app.services import session_title_service
        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(session_title_service, "system_llm", FakeSystemLLM())
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        test_agent.cli_tool = "claude_code"
        session_res = await test_client.post("/api/sessions", json={
            "title": test_agent.name,
            "agentConfigId": test_agent.id,
        })
        session_id = session_res.json()["id"]

        resp = await test_client.post(
            f"/api/sessions/{session_id}/chat",
            json={"content": "测试常驻进程完成信号"},
        )
        events = []
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        assert any(event.get("type") == "agent.process.completed" for event in events)
        assert any(event.get("type") == "session.title_updated" for event in events)
        session = (await test_client.get(f"/api/sessions/{session_id}")).json()
        assert session["title"] == "常驻进程续聊"

    async def test_single_chat_keeps_manual_title(self, test_client, test_agent, monkeypatch):
        class FakeSystemLLM:
            def is_configured(self):
                return True

            async def chat(self, **kwargs):
                return SimpleNamespace(content="不应使用")

        from app.services import session_title_service
        monkeypatch.setattr(session_title_service, "system_llm", FakeSystemLLM())

        session_res = await test_client.post("/api/sessions", json={
            "title": "我的固定标题",
            "agentConfigId": test_agent.id,
        })
        session_id = session_res.json()["id"]

        await test_client.post(
            f"/api/sessions/{session_id}/chat",
            json={"content": "帮我优化登录页交互"},
        )

        session = (await test_client.get(f"/api/sessions/{session_id}")).json()
        assert session["title"] == "我的固定标题"

    @pytest.mark.parametrize(
        ("cli_tool", "engine_session_id", "metadata_source", "caller_assigned"),
        [
            ("claude_code", None, "claude_code_result", True),
            ("codex", "codex-engine-session-1", "codex_thread.started", False),
            ("opencode", "ses_opencode_1", "opencode_session.created", False),
        ],
    )
    async def test_cli_chat_reuses_captured_engine_session(
        self, test_client, db_session, monkeypatch,
        cli_tool, engine_session_id, metadata_source, caller_assigned,
    ):
        calls = []

        async def fake_stream(self, **kwargs):
            calls.append(kwargs)
            event_engine_session_id = (
                kwargs.get("engine_session_id") if caller_assigned else engine_session_id
            )
            yield CliEvent(
                "agent.metadata",
                "proc-1",
                chunk_type="metadata",
                metadata={
                    "engineSessionId": event_engine_session_id,
                    "engineSessionSource": metadata_source,
                    "cliTool": cli_tool,
                },
            )
            yield CliEvent(
                "agent.output",
                "proc-1",
                chunk="ok",
                chunk_type="text",
            )
            yield CliEvent("agent.process.completed", "proc-1", exit_code=0)

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        project = Project(
            id=str(uuid.uuid4()),
            name=f"{cli_tool} Resume 项目",
            workspace_path=str(BACKEND_ROOT / ".test-workspaces" / str(uuid.uuid4())),
            status="ready",
        )
        Path(project.workspace_path).mkdir(parents=True, exist_ok=True)
        agent = AgentConfig(
            id=str(uuid.uuid4()),
            name=f"{cli_tool} 测试",
            description=f"测试 {cli_tool} resume",
            system_prompt="",
            agent_type="cli_wrapper",
            cli_tool=cli_tool,
            executable=sys.executable,
            init_args="[]",
            env_vars="{}",
        )
        db_session.add(project)
        db_session.add(agent)
        await db_session.commit()

        session_res = await test_client.post("/api/sessions", json={
            "title": f"{cli_tool} Resume",
            "projectId": project.id,
            "agentConfigId": agent.id,
        })
        session_id = session_res.json()["id"]

        await test_client.post(f"/api/sessions/{session_id}/chat", json={"content": "第一轮"})
        await test_client.post(f"/api/sessions/{session_id}/chat", json={"content": "第二轮"})

        if caller_assigned:
            assert calls[0]["engine_session_mode"] == "start"
            assert calls[0]["engine_session_id"]
            uuid.UUID(calls[0]["engine_session_id"])
            expected_engine_session_id = calls[0]["engine_session_id"]
        else:
            assert calls[0]["engine_session_mode"] == "start"
            assert calls[0]["engine_session_id"] is None
            expected_engine_session_id = engine_session_id
        assert calls[1]["engine_session_mode"] == "resume"
        assert calls[1]["engine_session_id"] == expected_engine_session_id
        second_prompt = "\n".join(message["content"] for message in calls[1]["messages"])
        assert "第二轮" in second_prompt
        assert "第一轮" not in second_prompt

        row = await db_session.get(EngineSession, (await _engine_session_id(db_session)))
        assert row.cli_tool == cli_tool
        assert row.engine_session_id == expected_engine_session_id

    async def test_claude_chat_remembers_agenthub_assigned_session_without_metadata(
        self, test_client, db_session, monkeypatch,
    ):
        calls = []

        async def fake_stream(self, **kwargs):
            calls.append(kwargs)
            yield CliEvent(
                "agent.output",
                "proc-1",
                chunk="ok",
                chunk_type="text",
            )
            yield CliEvent("agent.process.completed", "proc-1", exit_code=0)

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        project = Project(
            id=str(uuid.uuid4()),
            name="Claude assigned session 项目",
            workspace_path=str(BACKEND_ROOT / ".test-workspaces" / str(uuid.uuid4())),
            status="ready",
        )
        Path(project.workspace_path).mkdir(parents=True, exist_ok=True)
        agent = AgentConfig(
            id=str(uuid.uuid4()),
            name="Claude assigned session 测试",
            description="测试 Claude --session-id 兜底持久化",
            system_prompt="",
            agent_type="cli_wrapper",
            cli_tool="claude_code",
            executable=sys.executable,
            init_args="[]",
            env_vars="{}",
        )
        db_session.add(project)
        db_session.add(agent)
        await db_session.commit()

        session_res = await test_client.post("/api/sessions", json={
            "title": "Claude assigned session",
            "projectId": project.id,
            "agentConfigId": agent.id,
        })
        session_id = session_res.json()["id"]

        await test_client.post(f"/api/sessions/{session_id}/chat", json={"content": "第一轮"})
        await test_client.post(f"/api/sessions/{session_id}/chat", json={"content": "第二轮"})

        assigned_id = calls[0]["engine_session_id"]
        assert calls[0]["engine_session_mode"] == "start"
        assert assigned_id
        uuid.UUID(assigned_id)
        assert calls[1]["engine_session_mode"] == "resume"
        assert calls[1]["engine_session_id"] == assigned_id

        row = await db_session.get(EngineSession, (await _engine_session_id(db_session)))
        assert row.cli_tool == "claude_code"
        assert row.engine_session_id == assigned_id
        assert json.loads(row.metadata_json)["source"] == "agenthub_assigned"

    async def test_claude_single_chat_reuses_session_process_between_turns(
        self, test_client, db_session, monkeypatch,
    ):
        calls = []

        async def fake_stream(self, **kwargs):
            calls.append(kwargs)
            process_id = "proc-claude-session"
            yield CliEvent(
                "agent.process.started",
                process_id,
                metadata={
                    "persistentProcess": True,
                    "reused": len(calls) > 1,
                    "recovered": False,
                    "engineSessionMode": kwargs.get("engine_session_mode"),
                    "engineSessionId": kwargs.get("engine_session_id"),
                },
            )
            yield CliEvent(
                "agent.output",
                process_id,
                chunk=f"turn-{len(calls)}",
                chunk_type="text",
            )
            yield CliEvent(
                "agent.process.turn_completed",
                process_id,
                exit_code=0,
                metadata={"persistentProcess": True},
            )

        from app.services.cli_agent_service import CliAgentService
        monkeypatch.setattr(CliAgentService, "stream", fake_stream)

        project = Project(
            id=str(uuid.uuid4()),
            name="Claude persistent process 项目",
            workspace_path=str(BACKEND_ROOT / ".test-workspaces" / str(uuid.uuid4())),
            status="ready",
        )
        Path(project.workspace_path).mkdir(parents=True, exist_ok=True)
        agent = AgentConfig(
            id=str(uuid.uuid4()),
            name="Claude persistent process 测试",
            description="测试 Claude 会话级常驻进程",
            system_prompt="",
            agent_type="cli_wrapper",
            cli_tool="claude_code",
            executable=sys.executable,
            init_args="[]",
            env_vars="{}",
        )
        db_session.add(project)
        db_session.add(agent)
        await db_session.commit()

        session_res = await test_client.post("/api/sessions", json={
            "title": "Claude persistent process",
            "projectId": project.id,
            "agentConfigId": agent.id,
        })
        session_id = session_res.json()["id"]

        first = await test_client.post(f"/api/sessions/{session_id}/chat", json={"content": "第一轮"})
        second = await test_client.post(f"/api/sessions/{session_id}/chat", json={"content": "第二轮"})
        assert first.status_code == 200
        assert second.status_code == 200

        assert calls[0]["persistent_process"] is True
        assert calls[1]["persistent_process"] is True
        assert calls[0]["engine_session_mode"] == "start"
        assert calls[0]["engine_session_id"]
        assert calls[1]["engine_session_mode"] == "resume"
        assert calls[1]["engine_session_id"] == calls[0]["engine_session_id"]

        runs = (await test_client.get(f"/api/sessions/{session_id}/runs")).json()
        assert [run["status"] for run in runs] == ["completed", "completed"]

        messages = (await test_client.get(f"/api/sessions/{session_id}/messages")).json()
        assistant_messages = [message for message in messages if message["role"] == "assistant"]
        assert len(assistant_messages) == 2
        metadata = assistant_messages[-1]["metadata"]
        assert metadata["engineRuntime"]["mode"] == "persistent_process"
        assert metadata["engineRuntime"]["persistentProcess"] is True
        assert metadata["engineRuntime"]["processKeptAlive"] is True
        assert metadata["engineRuntime"]["reused"] is True
        assert metadata["engineRuntime"]["engineSessionMode"] == "resume"
        assert metadata["engineRuntime"]["engineSessionId"] == calls[0]["engine_session_id"]
        trace_items = metadata["executionTrace"]["items"]
        assert trace_items[0]["title"] == "复用 Claude persistent process 测试 常驻进程"
        assert trace_items[0]["persistentProcess"] is True
        assert trace_items[-1]["title"] == "Claude persistent process 测试 本轮完成"

        process_rows = []
        for run in runs:
            process_rows.extend((await test_client.get(f"/api/runs/{run['id']}/processes")).json())
        assert len(process_rows) == 2
        assert {row["processId"] for row in process_rows} == {"proc-claude-session"}
        assert all(row["status"] == "completed" for row in process_rows)

    async def test_multiple_rounds_accumulate(self, test_client, test_session):
        """验证多轮对话消息累积。"""
        await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Round 1"},
        )
        await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Round 2"},
        )
        resp = await test_client.get(f"/api/sessions/{test_session}/messages")
        messages = resp.json()
        assert len(messages) == 4  # 2 user + 2 assistant


async def _engine_session_id(db_session) -> str:
    from sqlalchemy import select

    result = await db_session.execute(select(EngineSession.id))
    return result.scalar_one()


@pytest.mark.asyncio
class TestMessagesEndpoint:
    async def test_empty_session(self, test_client, test_session):
        resp = await test_client.get(f"/api/sessions/{test_session}/messages")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_messages_well_formed(self, test_client, test_session):
        await test_client.post(
            f"/api/sessions/{test_session}/chat",
            json={"content": "Hello"},
        )
        resp = await test_client.get(f"/api/sessions/{test_session}/messages")
        messages = resp.json()
        for m in messages:
            assert "id" in m
            assert "sessionId" in m
            assert "role" in m
            assert "content" in m
            assert "createdAt" in m
            assert m["role"] in ("user", "assistant")
