from types import SimpleNamespace

import pytest

from app.application import send_message
from app.application.send_message import SendMessageCommand, SendMessageUseCase
from app.services.schemas import ChainConfigSchema, ChatRequest


class FakeLocalChat:
    instances = []
    calls = []

    def __init__(self, db, event_bus=None):
        self.db = db
        self.event_bus = event_bus
        type(self).instances.append(self)

    async def _stream(self):
        yield "local-event"

    def send_message_stream(
        self,
        session_id,
        content,
        mentions=None,
        *,
        parent_message_id=None,
        chain_config=None,
        attachment_ids=None,
    ):
        type(self).calls.append({
            "session_id": session_id,
            "content": content,
            "mentions": mentions,
            "parent_message_id": parent_message_id,
            "chain_config": chain_config,
            "attachment_ids": attachment_ids,
        })
        return self._stream()


class FakeCloudRuntime:
    instances = []
    calls = []

    def __init__(self, db, event_bus=None):
        self.db = db
        self.event_bus = event_bus
        type(self).instances.append(self)

    async def _stream(self, marker):
        yield marker

    def stream_chat(
        self,
        session_id,
        content,
        *,
        actor,
        parent_message_id=None,
        attachment_ids=None,
    ):
        type(self).calls.append({
            "method": "stream_chat",
            "session_id": session_id,
            "content": content,
            "actor": actor,
            "parent_message_id": parent_message_id,
            "attachment_ids": attachment_ids,
        })
        return self._stream("cloud-single-event")

    def stream_group_chat(
        self,
        session_id,
        content,
        *,
        actor,
        mentions=None,
        parent_message_id=None,
        attachment_ids=None,
    ):
        type(self).calls.append({
            "method": "stream_group_chat",
            "session_id": session_id,
            "content": content,
            "actor": actor,
            "mentions": mentions,
            "parent_message_id": parent_message_id,
            "attachment_ids": attachment_ids,
        })
        return self._stream("cloud-group-event")


@pytest.fixture(autouse=True)
def use_fake_runtimes(monkeypatch):
    FakeLocalChat.instances = []
    FakeLocalChat.calls = []
    FakeCloudRuntime.instances = []
    FakeCloudRuntime.calls = []
    monkeypatch.setattr(send_message, "ChatServiceImpl", FakeLocalChat)
    monkeypatch.setattr(send_message, "CloudAgentRuntimeService", FakeCloudRuntime)


async def _collect(stream):
    return [item async for item in stream]


@pytest.mark.asyncio
async def test_local_workspace_routes_to_local_chat_service():
    db = object()
    event_bus = object()
    chain_config = ChainConfigSchema(chain_name="review", agent_order=["a", "b"])
    request = ChatRequest(
        content="hello",
        mentions=["agent-a"],
        parent_message_id="parent-1",
        chain_config=chain_config,
        attachment_ids=["attachment-1"],
    )

    stream = SendMessageUseCase(db, event_bus=event_bus).execute(
        SendMessageCommand(
            session=SimpleNamespace(id="session-1", mode="single"),
            project=SimpleNamespace(workspace_mode="local"),
            request=request,
        ),
    )

    assert await _collect(stream) == ["local-event"]
    assert FakeLocalChat.instances[0].db is db
    assert FakeLocalChat.instances[0].event_bus is event_bus
    assert FakeCloudRuntime.calls == []
    assert FakeLocalChat.calls == [{
        "session_id": "session-1",
        "content": "hello",
        "mentions": ["agent-a"],
        "parent_message_id": "parent-1",
        "chain_config": chain_config,
        "attachment_ids": ["attachment-1"],
    }]


@pytest.mark.asyncio
async def test_cloud_single_session_routes_to_cloud_runtime():
    actor = object()
    request = ChatRequest(
        content="ship it",
        parent_message_id="parent-2",
        attachment_ids=["attachment-2"],
    )

    stream = SendMessageUseCase(object(), event_bus="bus").execute(
        SendMessageCommand(
            session=SimpleNamespace(id="session-2", mode="single"),
            project=SimpleNamespace(workspace_mode="cloud"),
            request=request,
            actor=actor,
        ),
    )

    assert await _collect(stream) == ["cloud-single-event"]
    assert FakeLocalChat.calls == []
    assert FakeCloudRuntime.instances[0].event_bus == "bus"
    assert FakeCloudRuntime.calls == [{
        "method": "stream_chat",
        "session_id": "session-2",
        "content": "ship it",
        "actor": actor,
        "parent_message_id": "parent-2",
        "attachment_ids": ["attachment-2"],
    }]


@pytest.mark.asyncio
async def test_cloud_group_session_routes_to_cloud_group_runtime():
    actor = object()
    request = ChatRequest(
        content="plan together",
        mentions=["agent-a", "agent-b"],
        parent_message_id="parent-3",
        attachment_ids=["attachment-3"],
    )

    stream = SendMessageUseCase(object()).execute(
        SendMessageCommand(
            session=SimpleNamespace(id="session-3", mode="group"),
            project=SimpleNamespace(workspace_mode="cloud"),
            request=request,
            actor=actor,
        ),
    )

    assert await _collect(stream) == ["cloud-group-event"]
    assert FakeLocalChat.calls == []
    assert FakeCloudRuntime.calls == [{
        "method": "stream_group_chat",
        "session_id": "session-3",
        "content": "plan together",
        "actor": actor,
        "mentions": ["agent-a", "agent-b"],
        "parent_message_id": "parent-3",
        "attachment_ids": ["attachment-3"],
    }]
